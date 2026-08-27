import io
import re
from difflib import SequenceMatcher
from datetime import datetime, timezone

import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.core.security import get_current_user
from backend.app.models import Vehicle, GateEvent

router = APIRouter(prefix="/gate", tags=["Gate"])


def vehicle_data(vehicle: Vehicle):
    return {
        "id": vehicle.id,
        "plate_number": vehicle.plate_number,
        "registration_number": vehicle.registration_number,
        "chassis_number": vehicle.chassis_number,
        "owner_nin_number": vehicle.owner_nin_number,
        "phone_number": vehicle.phone_number,
        "owner_department": vehicle.owner_department,
        "owner_address": vehicle.owner_address,
        "vehicle_type": vehicle.vehicle_type,
        "make": vehicle.make,
        "model": vehicle.model,
        "color": vehicle.color,
    }


def normalize_plate(value: str) -> str:
    value = value.upper().strip()

    # OCR commonly inserts spaces, hyphens and punctuation.
    value = re.sub(r"[^A-Z0-9]", "", value)

    return value[:20]


# OCR character pairs that are commonly confused.
#
# These are used ONLY when comparing OCR candidates with
# registered database plates. We do not silently rewrite the
# original OCR result.
OCR_CONFUSION_PAIRS = (
    ("O", "0"),
    ("I", "1"),
    ("Z", "2"),
    ("S", "5"),
    ("B", "8"),
    ("G", "6"),
    ("T", "7"),
    ("E", "3"),
)


def generate_ocr_variants(
    candidate: str,
    max_changes: int = 2,
) -> list[str]:
    """
    Generate conservative OCR correction variants.

    The original candidate is always retained.
    At most max_changes character substitutions are made.
    """
    candidate = normalize_plate(candidate)

    if not candidate:
        return []

    variants = {candidate}
    current = {candidate}

    pair_map = {}

    for left, right in OCR_CONFUSION_PAIRS:
        pair_map[left] = right
        pair_map[right] = left

    for _ in range(max_changes):
        new_variants = set()

        for value in current:

            for index, char in enumerate(value):

                replacement = pair_map.get(char)

                if replacement is None:
                    continue

                variant = (
                    value[:index]
                    + replacement
                    + value[index + 1:]
                )

                if variant not in variants:
                    new_variants.add(variant)

        variants.update(new_variants)
        current = new_variants

        if not current:
            break

    return sorted(variants)


def plate_similarity(
    left: str,
    right: str,
) -> float:
    """
    Conservative similarity score for normalized plate strings.
    """
    left = normalize_plate(left)
    right = normalize_plate(right)

    if not left or not right:
        return 0.0

    if abs(len(left) - len(right)) > 1:
        return 0.0

    sequence_score = SequenceMatcher(
        None,
        left,
        right,
    ).ratio()

    max_length = max(
        len(left),
        len(right),
    )

    positional_matches = sum(
        1
        for index in range(
            min(len(left), len(right))
        )
        if left[index] == right[index]
    )

    positional_score = (
        positional_matches / max_length
    )

    return (
        (sequence_score * 0.70)
        + (positional_score * 0.30)
    )


def database_plate_match(
    candidate: str,
    db: Session,
):
    """
    Match an OCR candidate against the registered vehicle database.

    Priority:
    1. Exact OCR candidate.
    2. Exact OCR-confusion variant.
    3. Safe fuzzy database match.

    Returns:
        {
            "vehicle": Vehicle | None,
            "matched_plate": str | None,
            "method": str | None,
            "similarity": float,
            "margin": float,
        }
    """
    candidate = normalize_plate(candidate)

    if not candidate:
        return {
            "vehicle": None,
            "matched_plate": None,
            "method": None,
            "similarity": 0.0,
            "margin": 0.0,
        }

    variants = generate_ocr_variants(
        candidate,
        max_changes=2,
    )

    # ---------------------------------------------------------
    # 1. Exact database match against the OCR candidate itself.
    # ---------------------------------------------------------
    vehicle = db.scalar(
        select(Vehicle).where(
            Vehicle.plate_number == candidate
        )
    )

    if vehicle is not None:
        return {
            "vehicle": vehicle,
            "matched_plate": vehicle.plate_number,
            "method": "EXACT_OCR",
            "similarity": 1.0,
            "margin": 1.0,
        }

    # ---------------------------------------------------------
    # 2. Exact database match against OCR confusion variants.
    # ---------------------------------------------------------
    for variant in variants:

        if variant == candidate:
            continue

        vehicle = db.scalar(
            select(Vehicle).where(
                Vehicle.plate_number == variant
            )
        )

        if vehicle is not None:
            return {
                "vehicle": vehicle,
                "matched_plate": vehicle.plate_number,
                "method": "EXACT_OCR_VARIANT",
                "similarity": 0.97,
                "margin": 0.97,
            }

    # ---------------------------------------------------------
    # 3. Safe fuzzy matching.
    #
    # Only compare against plates with the same length or one
    # character difference. This prevents unrelated text from
    # producing false matches.
    # ---------------------------------------------------------
    minimum_length = max(
        3,
        len(candidate) - 1,
    )

    maximum_length = min(
        20,
        len(candidate) + 1,
    )

    vehicles = db.scalars(
        select(Vehicle).where(
            func.length(
                Vehicle.plate_number
            ).between(
                minimum_length,
                maximum_length,
            )
        )
    ).all()

    if not vehicles:
        return {
            "vehicle": None,
            "matched_plate": None,
            "method": None,
            "similarity": 0.0,
            "margin": 0.0,
        }

    ranked = []

    for vehicle in vehicles:

        best_score = 0.0
        best_source = candidate

        for variant in variants:

            score = plate_similarity(
                variant,
                vehicle.plate_number,
            )

            if score > best_score:
                best_score = score
                best_source = variant

        ranked.append(
            {
                "vehicle": vehicle,
                "score": best_score,
                "source": best_source,
            }
        )

    ranked.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    best = ranked[0]

    second_score = (
        ranked[1]["score"]
        if len(ranked) > 1
        else 0.0
    )

    margin = (
        best["score"]
        - second_score
    )

    # Strict safety thresholds.
    #
    # A fuzzy match is accepted only when:
    # - similarity is strong, and
    # - it is clearly better than the next candidate.
    if (
        best["score"] >= 0.90
        and margin >= 0.06
    ):
        return {
            "vehicle": best["vehicle"],
            "matched_plate": best[
                "vehicle"
            ].plate_number,
            "method": "FUZZY_DATABASE",
            "similarity": best["score"],
            "margin": margin,
        }

    return {
        "vehicle": None,
        "matched_plate": None,
        "method": None,
        "similarity": best["score"],
        "margin": margin,
    }


def perform_check(
    plate_number: str,
    db: Session,
    plate_confidence: float = 1.0,
):
    normalized_plate = normalize_plate(plate_number)

    if not normalized_plate:
        raise HTTPException(
            status_code=400,
            detail="Plate number is required",
        )

    vehicle = db.scalar(
        select(Vehicle).where(
            Vehicle.plate_number == normalized_plate
        )
    )

    if vehicle is not None:
        event = GateEvent(
            vehicle_id=vehicle.id,
            detected_plate_number=normalized_plate,
            plate_confidence=plate_confidence,
            vehicle_confidence=1.0,
            decision="ALLOW",
            decision_reason="REGISTERED_VEHICLE",
            hardware_status="PENDING",
        )

        db.add(event)
        db.commit()
        db.refresh(event)

        return {
            "status": "ALLOW",
            "gate_event_id": event.id,
            "vehicle_found": True,
            "vehicle": vehicle_data(vehicle),
            "detected_plate": normalized_plate,
            "plate_confidence": plate_confidence,
        }

    event = GateEvent(
        vehicle_id=None,
        detected_plate_number=normalized_plate,
        plate_confidence=plate_confidence,
        vehicle_confidence=None,
        decision="CHECK",
        decision_reason="VEHICLE_NOT_FOUND",
        hardware_status="PENDING",
    )

    db.add(event)
    db.commit()
    db.refresh(event)

    return {
        "status": "CHECK",
        "gate_event_id": event.id,
        "vehicle_found": False,
        "vehicle": None,
        "detected_plate": normalized_plate,
        "plate_confidence": plate_confidence,
    }


@router.post("/check")
def check_vehicle(
    plate_number: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return perform_check(
        plate_number=plate_number,
        db=db,
        plate_confidence=1.0,
    )


@router.post("/photo-check")
async def photo_check(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if (
        not file.content_type
        or not file.content_type.startswith("image/")
    ):
        raise HTTPException(
            status_code=400,
            detail="Please upload an image of the vehicle plate.",
        )

    image_bytes = await file.read()

    if not image_bytes:
        raise HTTPException(
            status_code=400,
            detail="The uploaded image is empty.",
        )

    try:
        image = Image.open(
            io.BytesIO(image_bytes)
        )

        image = ImageOps.exif_transpose(
            image
        ).convert("RGB")

        original_width, original_height = image.size

        # Enlarge smaller photographs before OCR.
        if original_width < 1200:
            scale = 1200 / max(original_width, 1)

            image = image.resize(
                (
                    int(original_width * scale),
                    int(original_height * scale),
                ),
                Image.Resampling.LANCZOS,
            )

        width, height = image.size

        # Several plate-focused crops.
        #
        # crop2 is the region that proved successful in the
        # direct Tesseract test: approximately 5%-96% width
        # and 13%-87% height.
        crop_boxes = [
            (
                "full",
                (
                    0,
                    0,
                    width,
                    height,
                ),
            ),
            (
                "plate_wide",
                (
                    int(width * 0.05),
                    int(height * 0.13),
                    int(width * 0.96),
                    int(height * 0.87),
                ),
            ),
            (
                "plate_center",
                (
                    int(width * 0.08),
                    int(height * 0.20),
                    int(width * 0.94),
                    int(height * 0.82),
                ),
            ),
        ]

        # OCR configurations that worked in direct testing.
        configs = (
            "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            "--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            "--psm 13 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        )

        raw_results = []

        for crop_name, box in crop_boxes:

            crop = image.crop(box)

            gray = ImageOps.grayscale(crop)
            gray = ImageOps.autocontrast(gray)

            gray = ImageEnhance.Contrast(
                gray
            ).enhance(3.0)

            gray = ImageEnhance.Sharpness(
                gray
            ).enhance(3.0)

            # Create several preprocessing variants.
            variants = [
                ("normal", gray),
                (
                    "threshold140",
                    gray.point(
                        lambda p: 255
                        if p > 140
                        else 0
                    ),
                ),
                (
                    "threshold170",
                    gray.point(
                        lambda p: 255
                        if p > 170
                        else 0
                    ),
                ),
            ]

            for variant_name, processed in variants:

                processed = processed.resize(
                    (
                        processed.width * 3,
                        processed.height * 3,
                    ),
                    Image.Resampling.LANCZOS,
                )

                for config in configs:

                    raw_text = pytesseract.image_to_string(
                        processed,
                        config=config,
                    )

                    cleaned = normalize_plate(
                        raw_text
                    )

                    if not cleaned:
                        continue

                    # Break the OCR result into plausible plate
                    # candidates as well as preserving the full result.
                    pieces = re.findall(
                        r"[A-Z]{1,5}[0-9]{1,5}[A-Z]{0,4}"
                        r"|[A-Z0-9]{5,15}",
                        cleaned,
                    )

                    candidates = set(pieces)

                    if (
                        5 <= len(cleaned) <= 20
                    ):
                        candidates.add(cleaned)

                    for candidate in candidates:

                        candidate = normalize_plate(
                            candidate
                        )

                        if not (
                            5
                            <= len(candidate)
                            <= 20
                        ):
                            continue

                        raw_results.append(
                            {
                                "candidate": candidate,
                                "crop": crop_name,
                                "variant": variant_name,
                                "config": config,
                                "raw_text": raw_text.strip(),
                            }
                        )

        if not raw_results:
            return {
                "status": "OCR_FAILED",
                "vehicle_found": False,
                "detected_plate": None,
                "plate_confidence": 0.0,
                "ocr_status": "FAILED",
                "message": (
                    "Plate could not be read reliably. "
                    "Type the plate number manually "
                    "and search again."
                ),
            }

        # Count how consistently each candidate appears.
        scores = {}

        for item in raw_results:

            candidate = item["candidate"]

            if candidate not in scores:
                scores[candidate] = {
                    "count": 0,
                    "crops": set(),
                    "variants": set(),
                    "raw_texts": [],
                }

            scores[candidate]["count"] += 1
            scores[candidate]["crops"].add(
                item["crop"]
            )
            scores[candidate]["variants"].add(
                item["variant"]
            )

            if item["raw_text"]:
                scores[candidate]["raw_texts"].append(
                    item["raw_text"]
                )

        ranked = []

        for candidate, info in scores.items():

            score = (
                info["count"] * 2
                + len(info["crops"]) * 4
                + len(info["variants"]) * 2
            )

            # Plates containing both letters and numbers
            # are more plausible than plain text.
            has_letters = any(
                char.isalpha()
                for char in candidate
            )

            has_numbers = any(
                char.isdigit()
                for char in candidate
            )

            if has_letters and has_numbers:
                score += 5

            ranked.append(
                {
                    "candidate": candidate,
                    "score": score,
                    "count": info["count"],
                    "crop_count": len(
                        info["crops"]
                    ),
                    "variant_count": len(
                        info["variants"]
                    ),
                    "raw_texts": list(
                        dict.fromkeys(
                            info["raw_texts"]
                        )
                    ),
                }
            )

        ranked.sort(
            key=lambda item: (
                item["score"],
                item["crop_count"],
                item["variant_count"],
                item["count"],
            ),
            reverse=True,
        )

        # -----------------------------------------------------
        # DATABASE-AWARE OCR MATCHING
        #
        # Do not choose the highest OCR score blindly.
        # Search all strong OCR candidates and let a registered
        # database match take priority.
        # -----------------------------------------------------
        database_match = None

        for item in ranked:

            match = database_plate_match(
                candidate=item["candidate"],
                db=db,
            )

            if match["vehicle"] is not None:
                database_match = {
                    "ocr_candidate": item["candidate"],
                    **match,
                }

                break

        if database_match is not None:

            matched_vehicle = database_match[
                "vehicle"
            ]

            matched_plate = database_match[
                "matched_plate"
            ]

            method = database_match[
                "method"
            ]

            similarity = database_match[
                "similarity"
            ]

            if method == "EXACT_OCR":
                confidence = 0.98

            elif method == "EXACT_OCR_VARIANT":
                confidence = 0.95

            else:
                confidence = min(
                    max(
                        0.90,
                        similarity,
                    ),
                    0.97,
                )

            result = perform_check(
                plate_number=matched_plate,
                db=db,
                plate_confidence=confidence,
            )

            result["ocr_status"] = "SUCCESS"
            result["ocr_match_method"] = method
            result["ocr_original_candidate"] = (
                database_match["ocr_candidate"]
            )
            result["ocr_matched_plate"] = matched_plate
            result["ocr_similarity"] = round(
                similarity,
                4,
            )

            result["ocr_raw_text"] = " | ".join(
                ranked_item["candidate"]
                for ranked_item in ranked[:10]
            )

            result["ocr_candidates"] = ranked[
                :10
            ]

            return result

        # No exact database match.
        #
        # For an unregistered plate we require repeated
        # agreement before trusting the OCR result.
        best = ranked[0]

        if (
            best["crop_count"] < 1
            or best["variant_count"] < 2
            or best["score"] < 9
        ):
            return {
                "status": "OCR_FAILED",
                "vehicle_found": False,
                "detected_plate": None,
                "plate_confidence": 0.0,
                "ocr_status": "LOW_CONFIDENCE",
                "ocr_candidates": ranked[:10],
                "message": (
                    "The plate image was not read "
                    "reliably. Type the plate number "
                    "manually and search again."
                ),
            }

        detected_plate = best["candidate"]

        confidence = min(
            0.55
            + min(
                best["score"] / 100.0,
                0.30,
            ),
            0.85,
        )

        result = perform_check(
            plate_number=detected_plate,
            db=db,
            plate_confidence=confidence,
        )

        result["ocr_status"] = "SUCCESS_UNREGISTERED"
        result["ocr_raw_text"] = " | ".join(
            best["raw_texts"]
        )
        result["ocr_candidates"] = ranked[:10]

        return result

 except Exception as exc:
    import traceback

    print("========== PHOTO OCR ERROR ==========")
    traceback.print_exc()
    print("=====================================")

    raise HTTPException(
        status_code=400,
        detail=f"Could not process the image: {exc}",
    )


@router.get("/history")
def gate_history(
    plate_number: str,
    db: Session = Depends(get_db),
):
    normalized_plate = normalize_plate(plate_number)

    if not normalized_plate:
        raise HTTPException(
            status_code=400,
            detail="Plate number is required",
        )

    events = db.scalars(
        select(GateEvent)
        .where(
            GateEvent.detected_plate_number == normalized_plate
        )
        .order_by(GateEvent.detected_at.desc())
        .limit(20)
    ).all()

    return {
        "plate_number": normalized_plate,
        "count": len(events),
        "history": [
            {
                "id": event.id,
                "detected_plate_number": event.detected_plate_number,
                "decision": event.decision,
                "decision_reason": event.decision_reason,
                "plate_confidence": event.plate_confidence,
                "vehicle_confidence": event.vehicle_confidence,
                "camera_id": event.camera_id,
                "gate_id": event.gate_id,
                "hardware_status": event.hardware_status,
                "detected_at": (
                    event.detected_at.isoformat()
                    if event.detected_at
                    else None
                ),
                "processed_at": (
                    event.processed_at.isoformat()
                    if event.processed_at
                    else None
                ),
            }
            for event in events
        ],
    }
