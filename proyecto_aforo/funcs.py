import cv2

# ===== COLORES POR CLASE =====
COLORES_CLASE = {
    0: (0, 255, 0),    # persona -> verde
    2: (255, 100, 0),  # carro   -> azul
}

def dibujar_detecciones(frame, results):
    """Dibuja bounding boxes y confianza por clase con colores distintos."""
    for box in results[0].boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        conf  = float(box.conf[0])
        clase = int(box.cls[0])

        color = COLORES_CLASE.get(clase, (200, 200, 200))

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, f"{conf:.2f}",
                    (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

def mostrar_frame(frame, fps, ventana="NCNN YOLO Camera", activo=True):
    """Muestra el frame en una ventana. Se puede desactivar con activo=False."""
    if activo:
        cv2.putText(frame, f"FPS total: {fps:.2f}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow(ventana, frame)
