import os

# Real (AI-generated, non-real-person) face photos shared across the demo
# scenario runner and the free-text screening flow's auto-simulated capture.
# Hand-drawn cartoon avatars don't carry enough facial structure for a
# properly trained deep face model (MTCNN + InceptionResnetV1) to even
# detect as a face, let alone discriminate on -- a real photo is required
# for a genuine match/mismatch result rather than a meaningless comparison
# of two undetected avatar crops.
_DEMO_FACES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "demo-data", "faces"))
PERSON_A = os.path.join(_DEMO_FACES_DIR, "person_a.jpg")
PERSON_B = os.path.join(_DEMO_FACES_DIR, "person_b.jpg")
