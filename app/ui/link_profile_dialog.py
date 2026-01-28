from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainterPath, QPen
from PySide6.QtWidgets import QDialog, QGraphicsPathItem, QGraphicsScene, QGraphicsView, QLabel, QVBoxLayout

from app.link_analyzer import LinkProfile


class LinkProfileDialog(QDialog):
    def __init__(self, profile: LinkProfile, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Профіль траси")
        self.resize(640, 360)

        status_label = QLabel(
            f"Статус: {profile.status} | Потрібно підняти: {profile.clearance_needed_m:.1f} м",
            self,
        )

        scene = QGraphicsScene(self)
        view = QGraphicsView(scene, self)
        view.setRenderHint(view.renderHints())
        view.setBackgroundBrush(Qt.GlobalColor.white)

        path = QPainterPath()
        max_elev = max(profile.elevations_m) if profile.elevations_m else 1
        max_dist = max(profile.distances_km) if profile.distances_km else 1
        width = 560
        height = 200
        for idx, (d, elev) in enumerate(zip(profile.distances_km, profile.elevations_m)):
            x = (d / max_dist) * width
            y = height - (elev / max_elev) * height
            if idx == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        item = QGraphicsPathItem(path)
        item.setPen(QPen(Qt.GlobalColor.darkGreen, 2))
        scene.addItem(item)
        scene.setSceneRect(0, 0, width, height)

        layout = QVBoxLayout(self)
        layout.addWidget(status_label)
        layout.addWidget(view)
        self.setLayout(layout)
