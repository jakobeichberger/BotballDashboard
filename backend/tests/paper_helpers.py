"""Shared helpers for paper-review tests.

A paper can only be submitted with a PDF version, and reviews are only
accepted once it is submitted, so most tests need these steps first.
"""

from sqlalchemy import select

from core.auth import create_access_token
from modules.auth.models import Permission, Role, RolePermission, User, UserRole
from modules.auth.service import hash_password

PDF = b"%PDF-1.5 paper review test"

# All five criteria filled: required to submit a review.
FULL_SCORES = {
    "score_content": 8.0,
    "score_implementation": 6.0,
    "score_results": 7.0,
    "score_language": 9.0,
    "score_format": 10.0,
}  # mean 8.0


async def api_upload(client, headers, paper_id, content: bytes = PDF, name="paper.pdf"):
    resp = await client.post(
        f"/api/papers/{paper_id}/upload",
        headers=headers,
        files={"file": (name, content, "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def api_upload_and_submit(client, headers, paper_id):
    await api_upload(client, headers, paper_id)
    resp = await client.put(f"/api/papers/{paper_id}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def add_version(db, paper_id: str, uploaded_by: str | None = None):
    """Unit-test shortcut: record a version row without touching the disk."""
    from modules.paper_review.models import Paper, PaperVersion

    paper = await db.get(Paper, paper_id)
    number = (paper.current_version or 0) + 1
    db.add(
        PaperVersion(
            paper_id=paper_id,
            version_number=number,
            revision_number=paper.revision_number,
            file_name="paper.pdf",
            storage_path=f"papers/{paper_id}/v{number}/paper.pdf",
            file_size_bytes=10,
            uploaded_by=uploaded_by,
        )
    )
    paper.current_version = number
    paper.file_name = "paper.pdf"
    await db.flush()


async def submitted_paper(db, data: dict, user_id: str):
    """Create a paper, give it a version and submit it."""
    from modules.paper_review.service import create_paper, submit_paper

    paper = await create_paper(db, data)
    await add_version(db, paper.id)
    return await submit_paper(db, paper.id, user_id)


async def make_user(db, email: str, permissions: tuple[str, ...] = ()) -> User:
    """Non-superuser holding exactly `permissions` (through a role of its own)."""
    user = User(
        email=email,
        display_name=email.split("@")[0],
        hashed_password=hash_password("password123"),
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()
    if permissions:
        role = Role(name=f"role-{email}")
        db.add(role)
        await db.flush()
        for name in permissions:
            perm = (
                await db.execute(select(Permission).where(Permission.name == name))
            ).scalar_one_or_none()
            if perm is None:
                perm = Permission(name=name, description=name)
                db.add(perm)
                await db.flush()
            db.add(RolePermission(role_id=role.id, permission_id=perm.id))
        db.add(UserRole(user_id=user.id, role_id=role.id))
    await db.commit()
    await db.refresh(user)
    return user


def headers_for(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}
