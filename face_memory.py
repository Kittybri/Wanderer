"""Local YuNet/SFace embeddings. Explicit enrollment only; no image retention."""
from __future__ import annotations
import hashlib
import io
import math
import os
import threading
import time
from pathlib import Path

BACKEND = "opencv-yunet-sface-v1"
try:
    FACE_MATCH_THRESHOLD = float(os.getenv("FACE_COSINE_THRESHOLD","0.55"))
    if not math.isfinite(FACE_MATCH_THRESHOLD) or not 0.3 <= FACE_MATCH_THRESHOLD <= 0.99:
        FACE_MATCH_THRESHOLD = 0.55
except ValueError:
    FACE_MATCH_THRESHOLD = 0.55
MAX_FACE_TEMPLATES = 8
_lock = threading.RLock()
_models = None

def face_support_ready():
    return bool(os.path.isfile(os.getenv("FACE_YUNET_MODEL","")) and os.path.isfile(os.getenv("FACE_SFACE_MODEL","")))

def _load():
    global _models
    if _models is None:
        import cv2
        paths = [os.environ["FACE_YUNET_MODEL"],os.environ["FACE_SFACE_MODEL"]]
        digest = hashlib.sha256()
        for path in paths:
            with open(path,"rb") as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b""):
                    digest.update(chunk)
        detector=cv2.FaceDetectorYN.create(paths[0],"",(320,320),0.9,0.3,5000)
        recognizer=cv2.FaceRecognizerSF.create(paths[1],"")
        _models=(detector,recognizer,BACKEND+":"+digest.hexdigest())
    return _models

def extract_face_template(image_bytes):
    if not face_support_ready():
        return {"ok":False,"reason":"unavailable"}
    if not image_bytes or len(image_bytes)>8*1024*1024:
        return {"ok":False,"reason":"image_size"}
    try:
        from PIL import Image, ImageOps
        import cv2
        import numpy as np
        with Image.open(io.BytesIO(image_bytes)) as header:
            if header.width*header.height>16_000_000:
                return {"ok":False,"reason":"image_size"}
            image=cv2.cvtColor(np.asarray(ImageOps.exif_transpose(header).convert("RGB")),cv2.COLOR_RGB2BGR)
        if image is None:
            return {"ok":False,"reason":"decode_failed"}
        h,w=image.shape[:2]
        scale=min(1,1280/max(h,w))
        if scale<1:
            image=cv2.resize(image,(int(w*scale),int(h*scale)))
        with _lock:
            detector,recognizer,version=_load()
            detector.setInputSize((image.shape[1],image.shape[0]))
            _,faces=detector.detect(image)
            if faces is None or len(faces)==0:
                return {"ok":False,"reason":"no_face"}
            if len(faces)!=1:
                return {"ok":False,"reason":"ambiguous","face_count":len(faces)}
            face=faces[0]
            if min(face[2:4])<64:
                return {"ok":False,"reason":"face_too_small"}
            aligned=recognizer.alignCrop(image,face)
            if cv2.Laplacian(cv2.cvtColor(aligned,cv2.COLOR_BGR2GRAY),cv2.CV_64F).var()<20:
                return {"ok":False,"reason":"blurry"}
            vector=recognizer.feature(aligned).flatten().astype(float)
            vector/=max(float(np.linalg.norm(vector)),1e-12)
            return {"ok":True,"template":vector.tolist(),"model":version,"face_count":1,"quality":float(face[14])}
    except Exception:
        return {"ok":False,"reason":"backend_or_image_error"}

def _valid(vector):
    return isinstance(vector,list) and len(vector)==128 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in vector) and sum(v*v for v in vector)>0.5

def enroll_face_profile(profile,image_bytes):
    extracted=extract_face_template(image_bytes)
    if not extracted.get("ok"):
        return extracted
    profile=profile if isinstance(profile,dict) else {}
    same=profile.get("model")==extracted["model"]
    raw=profile.get("templates",[])
    templates=[t for t in raw if _valid(t)] if same and isinstance(raw,list) else []
    templates=(templates+[extracted["template"]])[-MAX_FACE_TEMPLATES:]
    return {"ok":True,"profile":{"backend":BACKEND,"model":extracted["model"],"templates":templates,
            "sample_count":len(templates),"updated_ts":time.time()},"sample_count":len(templates)}

def match_candidates(vector,candidates,model,threshold=None,margin=0.08):
    threshold=FACE_MATCH_THRESHOLD if threshold is None else max(0.3,min(0.99,threshold))
    if not _valid(vector):
        return {"ok":False,"reason":"corrupt_template","matched":False}
    ranked=[]
    for uid,profile in candidates.items():
        if not isinstance(profile,dict) or not isinstance(profile.get("templates"),list):
            continue
        if profile.get("backend")!=BACKEND or profile.get("model")!=model:
            continue
        scores=[]
        for template in profile.get("templates",[])[:MAX_FACE_TEMPLATES]:
            if _valid(template):
                dot=sum(a*b for a,b in zip(vector,template))
                norm=math.sqrt(sum(a*a for a in vector)*sum(b*b for b in template))
                scores.append(dot/norm)
        if scores:
            ranked.append((max(scores),uid))
    ranked.sort(reverse=True,key=lambda item:item[0])
    if not ranked:
        return {"ok":False,"reason":"legacy_or_corrupt_reenroll","matched":False}
    score,uid=ranked[0]
    ambiguous=len(ranked)>1 and score-ranked[1][0]<margin and score>=threshold
    matched=score>=threshold and not ambiguous
    return {"ok":True,"matched":matched,"status":"ambiguous" if ambiguous else ("match" if matched else "unknown"),
            "score":round(score,4),"threshold":threshold,"user_id":uid if matched else None}

def match_face(image_bytes,profile):
    if not isinstance(profile,dict) or not profile:
        return {"ok":False,"reason":"not_enrolled","matched":False}
    if profile.get("backend")!=BACKEND:
        return {"ok":False,"reason":"legacy_reenroll","matched":False}
    result=extract_face_template(image_bytes)
    if not result.get("ok"):
        return result
    return match_candidates(result["template"],{"self":profile},result["model"])

def enroll_face_profile_from_frames(profile,frames):
    result={"ok":False,"reason":"no_face"}
    for data,_ in (frames or [])[:5]:
        result=enroll_face_profile(profile,data)
        if result.get("ok"):
            return result
    return result

def match_face_frames(frames,profile):
    results=[match_face(data,profile) for data,_ in (frames or [])[:5]]
    good=[r for r in results if r.get("ok")]
    if not good:
        return results[0] if results else {"ok":False,"reason":"no_face"}
    # Never promote multiple uncertain frames into an identity claim.
    return max(good,key=lambda r:r.get("score",-1))

def is_face_enroll_request(text):
    return False  # Enrollment is exclusively an explicit command, not a keyword guess.

def is_face_check_request(text):
    return False  # Recognition is exclusively !recognizeface.
