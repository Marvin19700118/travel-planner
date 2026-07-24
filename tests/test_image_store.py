import image_store


def test_save_image_returns_a_url_path_and_stores_the_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(image_store, "IMAGE_DIR", tmp_path / "images")

    url = image_store.save_image("trip1", b"fake-bytes", extension="png")

    assert url.startswith("/images/trip1/")
    assert url.endswith(".png")
    filename = url.rsplit("/", 1)[-1]
    assert image_store.read_image("trip1", filename) == b"fake-bytes"


def test_read_image_returns_none_for_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(image_store, "IMAGE_DIR", tmp_path / "images")
    assert image_store.read_image("trip1", "does-not-exist.jpg") is None


def test_delete_trip_images_removes_the_whole_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(image_store, "IMAGE_DIR", tmp_path / "images")
    image_store.save_image("trip1", b"a", extension="jpg")
    image_store.save_image("trip1", b"b", extension="jpg")

    image_store.delete_trip_images("trip1")

    assert not (tmp_path / "images" / "trip1").exists()


def test_delete_trip_images_is_a_no_op_for_an_unknown_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(image_store, "IMAGE_DIR", tmp_path / "images")
    image_store.delete_trip_images("never-existed")  # should not raise


def test_save_image_detects_extension_from_real_bytes_when_unspecified(tmp_path, monkeypatch):
    monkeypatch.setattr(image_store, "IMAGE_DIR", tmp_path / "images")

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"rest-of-file"
    jpeg_bytes = b"\xff\xd8\xff" + b"rest-of-file"

    assert image_store.save_image("trip1", png_bytes).endswith(".png")
    assert image_store.save_image("trip1", jpeg_bytes).endswith(".jpg")


def test_media_type_for_matches_the_files_actual_extension():
    assert image_store.media_type_for("cover.png") == "image/png"
    assert image_store.media_type_for("cover.jpg") == "image/jpeg"
    assert image_store.media_type_for("cover.bin") == "application/octet-stream"


def test_read_image_rejects_path_traversal_in_trip_id(tmp_path, monkeypatch):
    monkeypatch.setattr(image_store, "IMAGE_DIR", tmp_path / "images")
    outside_file = tmp_path / "secret.txt"
    outside_file.write_bytes(b"top secret run log")

    assert image_store.read_image("..", "secret.txt") is None


def test_read_image_rejects_path_traversal_in_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(image_store, "IMAGE_DIR", tmp_path / "images")
    (tmp_path / "images" / "trip1").mkdir(parents=True)
    outside_file = tmp_path / "secret.txt"
    outside_file.write_bytes(b"top secret run log")

    assert image_store.read_image("trip1", "../../secret.txt") is None


def test_delete_trip_images_rejects_path_traversal_in_trip_id(tmp_path, monkeypatch):
    monkeypatch.setattr(image_store, "IMAGE_DIR", tmp_path / "images")
    outside_file = tmp_path / "secret.txt"
    outside_file.write_bytes(b"top secret run log")

    image_store.delete_trip_images("..")

    assert outside_file.exists()
