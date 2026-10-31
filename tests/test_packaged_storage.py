from fastapi.testclient import TestClient

from app.core import storage
from web import main


def test_packaged_upload_migration_preserves_existing_user_images(tmp_path, monkeypatch):
    install_dir = tmp_path / "Materiel"
    exe = install_dir / "Materiel.exe"
    exe.parent.mkdir()
    exe.touch()
    data_dir = tmp_path / "MaterielData"
    (install_dir / "materiel-data-dir.txt").write_text(str(data_dir), encoding="utf-8")
    legacy_uploads = install_dir / "_internal" / "static" / "uploads"
    legacy_file = legacy_uploads / "equipment-models" / "model.png"
    legacy_file.parent.mkdir(parents=True)
    legacy_file.write_bytes(b"legacy image")
    existing_file = data_dir / "uploads" / "spare-parts" / "part.png"
    existing_file.parent.mkdir(parents=True)
    existing_file.write_bytes(b"newer user image")
    monkeypatch.setattr(storage.sys, "executable", str(exe))
    monkeypatch.setattr(storage.sys, "frozen", True, raising=False)

    storage.migrate_packaged_uploads(install_dir / "_internal")

    assert (data_dir / "uploads" / "equipment-models" / "model.png").read_bytes() == b"legacy image"
    assert existing_file.read_bytes() == b"newer user image"
    legacy_file.write_bytes(b"changed legacy image")
    storage.migrate_packaged_uploads(install_dir / "_internal")
    assert (data_dir / "uploads" / "equipment-models" / "model.png").read_bytes() == b"legacy image"


def test_packaged_app_serves_uploads_from_persistent_data_directory(tmp_path, monkeypatch):
    install_dir = tmp_path / "Materiel"
    install_dir.mkdir()
    exe = install_dir / "Materiel.exe"
    exe.touch()
    data_dir = tmp_path / "MaterielData"
    uploads = data_dir / "uploads" / "equipment-models"
    uploads.mkdir(parents=True)
    (install_dir / "materiel-data-dir.txt").write_text(str(data_dir), encoding="utf-8")
    (uploads / "model.png").write_bytes(b"persistent user image")
    monkeypatch.setattr(main.sys, "executable", str(exe))
    monkeypatch.setattr(main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "create_default_admin", lambda: None)

    with TestClient(main.create_app()) as client:
        response = client.get("/static/uploads/equipment-models/model.png")

    assert response.status_code == 200
    assert response.content == b"persistent user image"
