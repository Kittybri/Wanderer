from __future__ import annotations

import os
import time

try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover - optional runtime dependency
    cv2 = None
    np = None


FACE_MATCH_THRESHOLD = float(os.getenv("FACE_MATCH_THRESHOLD", "0.18") or "0.18")
FACE_MATCH_LIKELY_THRESHOLD = float(os.getenv("FACE_MATCH_LIKELY_THRESHOLD", "0.24") or "0.24")
MAX_FACE_TEMPLATES = int(os.getenv("MAX_FACE_TEMPLATES", "8") or "8")
_ENROLL_PATTERNS = (
    "this is me",
    "that's me",
    "thats me",
    "this person is me",
    "that's my face",
    "remember my face",
    "remember what i look like",
    "learn my face",
    "keep my face in memory",
    "that's what i look like",
)
_CHECK_PATTERNS = (
    "is this me",
    "do you recognize me",
    "can you tell it's me",
    "do you know it's me",
    "is that me",
    "can you recognize me",
)


def _build_cascade():
    if cv2 is None:
        return None
    try:
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if cascade.empty():
            return None
        return cascade
    except Exception:
        return None


_FACE_CASCADE = _build_cascade()


def face_support_ready() -> bool:
    return cv2 is not None and np is not None and _FACE_CASCADE is not None


def is_face_enroll_request(text: str) -> bool:
    lowered = (text or "").lower()
    return any(pattern in lowered for pattern in _ENROLL_PATTERNS)


def is_face_check_request(text: str) -> bool:
    lowered = (text or "").lower()
    return any(pattern in lowered for pattern in _CHECK_PATTERNS)


def _decode_image(image_bytes: bytes):
    if not face_support_ready() or not image_bytes:
        return None
    data = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    return image


def _largest_face(gray_image):
    faces = _FACE_CASCADE.detectMultiScale(
        gray_image,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(64, 64),
    )
    if faces is None or len(faces) == 0:
        return None, 0
    best = max(faces, key=lambda rect: int(rect[2]) * int(rect[3]))
    return best, len(faces)


def _crop_face(gray_image, rect):
    x, y, w, h = [int(v) for v in rect]
    pad = int(max(w, h) * 0.18)
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(gray_image.shape[1], x + w + pad)
    y1 = min(gray_image.shape[0], y + h + pad)
    crop = gray_image[y0:y1, x0:x1]
    crop = cv2.resize(crop, (128, 128), interpolation=cv2.INTER_AREA)
    crop = cv2.equalizeHist(crop)
    return crop


def _lbp_histogram(face_crop):
    center = face_crop[1:-1, 1:-1]
    neighbors = [
        face_crop[:-2, :-2],
        face_crop[:-2, 1:-1],
        face_crop[:-2, 2:],
        face_crop[1:-1, 2:],
        face_crop[2:, 2:],
        face_crop[2:, 1:-1],
        face_crop[2:, :-2],
        face_crop[1:-1, :-2],
    ]
    codes = np.zeros_like(center, dtype=np.uint8)
    for bit, neighbor in enumerate(neighbors):
        codes |= ((neighbor >= center).astype(np.uint8) << bit)
    hist = np.bincount(codes.ravel(), minlength=256).astype(np.float32)
    total = float(hist.sum()) or 1.0
    hist /= total
    return hist


def extract_face_template(image_bytes: bytes) -> dict:
    if not face_support_ready():
        return {"ok": False, "reason": "unavailable"}
    image = _decode_image(image_bytes)
    if image is None:
        return {"ok": False, "reason": "decode_failed"}
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    rect, face_count = _largest_face(gray)
    if rect is None:
        return {"ok": False, "reason": "no_face", "face_count": 0}
    face_crop = _crop_face(gray, rect)
    hist = _lbp_histogram(face_crop)
    x, y, w, h = [int(v) for v in rect]
    quality = float((w * h) / max(1, gray.shape[0] * gray.shape[1]))
    return {
        "ok": True,
        "template": hist.tolist(),
        "face_count": int(face_count),
        "quality": quality,
        "face_box": [x, y, w, h],
    }


def _chi_square_distance(lhs, rhs) -> float:
    left = np.asarray(lhs, dtype=np.float32)
    right = np.asarray(rhs, dtype=np.float32)
    denom = left + right + 1e-8
    return float(0.5 * np.sum(((left - right) ** 2) / denom))


def _normalize_profile(profile: dict | None) -> dict:
    profile = dict(profile or {})
    templates = profile.get("templates") or []
    normalized = []
    for template in templates:
        if isinstance(template, list) and len(template) == 256:
            normalized.append(template)
    profile["templates"] = normalized[-MAX_FACE_TEMPLATES:]
    profile["sample_count"] = len(profile["templates"])
    return profile


def enroll_face_profile(existing_profile: dict | None, image_bytes: bytes) -> dict:
    extracted = extract_face_template(image_bytes)
    if not extracted.get("ok"):
        return extracted
    profile = _normalize_profile(existing_profile)
    templates = profile.get("templates", [])
    templates.append(extracted["template"])
    templates = templates[-MAX_FACE_TEMPLATES:]
    profile["templates"] = templates
    profile["sample_count"] = len(templates)
    profile["updated_ts"] = time.time()
    return {
        "ok": True,
        "profile": profile,
        "sample_count": len(templates),
        "quality": extracted.get("quality", 0.0),
        "face_count": extracted.get("face_count", 1),
    }


def enroll_face_profile_from_frames(existing_profile: dict | None, frames: list[tuple[bytes, str]]) -> dict:
    best = None
    for frame_bytes, _mime_type in frames or []:
        extracted = extract_face_template(frame_bytes)
        if not extracted.get("ok"):
            continue
        if best is None or float(extracted.get("quality", 0.0)) > float(best.get("quality", 0.0)):
            best = extracted
    if not best:
        return {"ok": False, "reason": "no_face"}
    profile = _normalize_profile(existing_profile)
    templates = profile.get("templates", [])
    templates.append(best["template"])
    templates = templates[-MAX_FACE_TEMPLATES:]
    profile["templates"] = templates
    profile["sample_count"] = len(templates)
    profile["updated_ts"] = time.time()
    return {
        "ok": True,
        "profile": profile,
        "sample_count": len(templates),
        "quality": best.get("quality", 0.0),
        "face_count": best.get("face_count", 1),
    }


def match_face(image_bytes: bytes, profile: dict | None) -> dict:
    profile = _normalize_profile(profile)
    templates = profile.get("templates", [])
    if not templates:
        return {"ok": False, "matched": False, "reason": "not_enrolled"}
    extracted = extract_face_template(image_bytes)
    if not extracted.get("ok"):
        return {"ok": False, "matched": False, "reason": extracted.get("reason", "no_face")}
    distances = [_chi_square_distance(extracted["template"], template) for template in templates]
    best = min(distances)
    status = "confirmed" if best <= FACE_MATCH_THRESHOLD else (
        "likely" if best <= FACE_MATCH_LIKELY_THRESHOLD else "no_match"
    )
    confidence = max(0.0, min(0.99, 1.0 - (best / max(FACE_MATCH_LIKELY_THRESHOLD, 1e-6))))
    return {
        "ok": True,
        "matched": status in {"confirmed", "likely"},
        "status": status,
        "distance": best,
        "confidence": confidence,
        "face_count": extracted.get("face_count", 1),
    }


def match_face_frames(frames: list[tuple[bytes, str]], profile: dict | None) -> dict:
    checked = []
    for frame_bytes, _mime_type in frames or []:
        result = match_face(frame_bytes, profile)
        if result.get("ok"):
            checked.append(result)
    if not checked:
        return {"ok": False, "matched": False, "reason": "no_face"}
    best = min(checked, key=lambda item: float(item.get("distance", 999.0)))
    matched_frames = sum(1 for item in checked if item.get("matched"))
    matched = bool(best.get("matched")) or matched_frames >= 2
    status = "confirmed" if best.get("status") == "confirmed" or matched_frames >= 2 else (
        "likely" if matched else "no_match"
    )
    confidence = max(
        float(best.get("confidence", 0.0)),
        min(0.99, (matched_frames / max(1, len(checked))) * 0.75),
    )
    return {
        "ok": True,
        "matched": matched,
        "status": status,
        "distance": float(best.get("distance", 999.0)),
        "confidence": confidence,
        "matched_frames": matched_frames,
        "checked_frames": len(checked),
    }
