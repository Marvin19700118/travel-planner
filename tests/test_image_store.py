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
