from app.service import load_items


class MainWindow:
    def show(self) -> None:
        _ = load_items()
