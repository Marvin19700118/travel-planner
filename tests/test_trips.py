import image_store
import trips


def test_save_and_list_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(trips, "TRIPS_DIR", tmp_path / "trips")

    record = {"trip_id": "abc", "city": "Paris", "days": 2, "start_date": "2026-08-01"}
    trips.save_trip("abc", record)

    assert trips.list_trips() == [record]


def test_list_trips_is_empty_when_nothing_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(trips, "TRIPS_DIR", tmp_path / "trips")
    assert trips.list_trips() == []


def test_delete_trip_removes_the_record_and_its_images(tmp_path, monkeypatch):
    monkeypatch.setattr(trips, "TRIPS_DIR", tmp_path / "trips")
    monkeypatch.setattr(image_store, "IMAGE_DIR", tmp_path / "images")

    trips.save_trip("abc", {"trip_id": "abc"})
    image_store.save_image("abc", b"cover", extension="jpg")

    deleted = trips.delete_trip("abc")

    assert deleted is True
    assert trips.list_trips() == []
    assert not (tmp_path / "images" / "abc").exists()


def test_delete_trip_returns_false_for_unknown_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(trips, "TRIPS_DIR", tmp_path / "trips")
    assert trips.delete_trip("never-existed") is False


def test_get_trip_returns_the_saved_record(tmp_path, monkeypatch):
    monkeypatch.setattr(trips, "TRIPS_DIR", tmp_path / "trips")
    record = {"trip_id": "abc", "city": "Paris"}
    trips.save_trip("abc", record)

    assert trips.get_trip("abc") == record


def test_get_trip_returns_none_for_unknown_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(trips, "TRIPS_DIR", tmp_path / "trips")
    assert trips.get_trip("never-existed") is None


def test_list_trips_is_sorted_by_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(trips, "TRIPS_DIR", tmp_path / "trips")
    trips.save_trip("b-trip", {"trip_id": "b-trip"})
    trips.save_trip("a-trip", {"trip_id": "a-trip"})

    result = trips.list_trips()

    assert [t["trip_id"] for t in result] == ["a-trip", "b-trip"]
