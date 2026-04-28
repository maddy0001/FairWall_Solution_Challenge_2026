"""
backend/setup/init_firestore.py
Creates Firestore composite indexes required by FairWall queries.
Run once before first deployment.

Usage:
    cd fairwall
    python -m backend.setup.init_firestore
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

PROJECT = os.getenv("GCP_PROJECT", "fairwall-2026")

try:
    from google.cloud import firestore
except ImportError:
    print("ERROR: google-cloud-firestore not installed.")
    sys.exit(1)


def main():
    """
    Seed Firestore with a placeholder document to initialise collections.
    Composite indexes (tenant_id + status + created_at etc.) must be created
    in the Firebase Console or via firebase.json — they cannot be created
    programmatically via the Python SDK.

    After running this script, go to:
    Firebase Console → Firestore → Indexes → Add composite index

    review_queue collection:
        Fields: tenant_id ASC, status ASC, created_at DESC

    interventions collection:
        Fields: tenant_id ASC, created_at DESC
    """
    print(f"Initialising Firestore for project: {PROJECT}")

    db = firestore.Client(project=PROJECT)

    # Create collections by seeding + deleting a sentinel document
    for collection in ["review_queue", "interventions"]:
        ref = db.collection(collection).document("_init_sentinel")
        ref.set({"_init": True, "tenant_id": "_system"})
        ref.delete()
        print(f"Collection initialised: {collection}")

    print("\nFirestore collections ready.")
    print("\nIMPORTANT — Create these composite indexes in Firebase Console:")
    print("  review_queue   : tenant_id ASC + status ASC + created_at DESC")
    print("  interventions  : tenant_id ASC + created_at DESC")
    print("\nOr deploy firestore.indexes.json if you have Firebase CLI configured.")


if __name__ == "__main__":
    main()
