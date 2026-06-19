from app.main import app


def test_import() -> None:
    assert app.title == "Telegram Mini Shop"


if __name__ == "__main__":
    test_import()
    print("ok")
