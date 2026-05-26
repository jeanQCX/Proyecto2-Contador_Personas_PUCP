import cv2
from ultralytics import YOLO
import time
from funcs import dibujar_detecciones, mostrar_frame

#------------------ Pruebas ------------------------------------------
#1.- 1.84 FPS primera prueba sin opti, uso de plot(), yolov8n -> basados en NCNN
#2.- 1.99 FPS todas las clases, resolucion 640x480 v4l2 y dibujo manual
#3.- 2.07 FPS algunas optimizaciones (clases solo persona y reduccion de resolucion a 416x256
 
#     av     mi     mx 
#4.-  2.06 | 1.87 | 2.21  FPS 416x256 y cambio formato de pixel to MJPG, no mucha diferencia con YUYV 
#5.-  2.05 | 1.94 | 2.23  FPS reduccion de resolucion to 320x190, yolov8n
#5.-  2.09 | 1.96 | 2.24  FPS reduccion de resolucion to 256x160, yolov8n

#7.-  2.24 | 1.44 | 2.35  FPS resolucion de 416x256, yolov5nu 
#8.-  2.16 | 1.56 | 2.37  FPS reduccion de resolucion to 320x190, yolov5nu 640x640
#9.-  2.17 | 1.98 | 2.30  FPS reduccion de resolucion to 256x160, yolov5nu 640x640

#10.- 0.97 | 0.59 | 1.02  FPS resolucion 416x256, modelo yolov5nu.pt basado en Torch

#11.- 5.90 | 4.55 | 7.12  FPS r256x160, YOLO 320x320, yolov5nu_rx320  (similar a #13) <---
#12.- 9.35 | 5.89 | 13.18 FPS r256x160, YOLO 160x160, yolov5nu_rx160 obs:muy inestable

#13.- 6.21 | 4.43 | 7.16  FPS r256x160, YOLO 320x320, yolov5nu_rx320_v1 => simplify=True  obs: optimize=True no compatible con ncnn, 10.2 MB, simplify existe??  # :3
#14.- 5.87 | 4.28 | 7.10  FPS r256x160, YOLO 320x320, yolov5nu_rx320_v2 => half=True obs: FP16, 5.2 MB
#15.- 5.75 | 4.53 | 6.88  FPS r256x160, YOLO 320x320, yolov5nu_rx320_v3 => half=True simplify=True obs: 5.2 MB

#16.- 5.99 | 4.57 | 6.95  FPS r256x160, YOLO 320x320, yolo26n => device=cpu OBS:da igual ese device, 9.6 MB

#17.- 7.67 | 6.62 | 8.09  FPS r256x160, YOLO 320x320, yolo26n obs: parametros de inferencia device cpu, conf 0.5, iou 0.45, 2 clases,VERBOSE FALSE (+1.67 FPS) a comp #16 <----      
#18.- 7.23 | 6.12 | 7.84  FPS v4l2-r320x240 y buffer=1, YOLO 320x320, yolo26n obs: estables mediciones seguidas, no hay mucha variacion entre pruebas ->repetibilidad, pero baja precision
#19.- 2.18 | 2.08 | 2.27  FPS v4l2-r640x480 YOLO640x640, yolo26n obs: aumento la calidad de la precision, ahora detecta mas personas, pero los fps cayeron

#int8 comp
#20.- 5.17 | 4.53 | 5.56  FPS v4l2-r640x480 YOLO 320x320, yolo26n obs: precision OK
#21.- 5.33 | 4.54 | 5.78  FPS v4l2-r640x480 YOLO 320x320, yolo26n_int8 obs: precision NADA
#22.- 6.88 | 6.19 | 7.26  FPS v4l2-r640x480 YOLO 320x320, yolo26n_int8.mnn obs: precision media?

#23.- 7.10 | 6.13 | 7.79  FPS v4l2-r640x480 YOLO 320x320, yolo26n, sin funcion de dibujo ni dFPS obs: aumento de FPS (+1.71 FPS, pero de sistema) a comp de #20  <---- 

# LEARNINGS: 
#yolor320x320 (de ahi, un pco mas pequeño, o un pco mas grande, trade-off FPS y precision)
#verbose FALSE da +1.67 FPS, y sin func dibujo +1.71 FPS, aprox en embebido sera un total de +3 FPS (ojo, FPS sistema)
#resolciones : captura -> resize -> yolo320x320 = 3 transformaciones, cual es la mejor forma?


# ===== CONFIGURACION =====
DURACION_SEGUNDOS = 60  # duracion segundos de la prueba

# ===== CARGA DEL MODELO =====
#model = YOLO("yolov5nu.pt")
#model = YOLO("yolo26n_ncnn_model", task="detect")
model = YOLO("yolo26n_rx256_ncnn_model", task="detect")
#model = YOLO("yolo26n_int8_r256vf.mnn", task="detect")

#model = YOLO("yolo26n_INT8.mnn", task="detect")
#model = YOLO("yolo26n_int8_ncnn_model", task="detect")
#model = YOLO("yolov5nu_rx320_v3_ncnn_model", task="detect")

# ===== VIDEO =====
#Teros_v2c1.mp4 -> 10s   Teros_v1c2.mp4 -> 15s   Teros_v2c3.mp4 -> 48s   Teros_v1c4.mp4 -> 53s   Teros_v3c5.mp4 -> 117s
#cap = cv2.VideoCapture("video_pcamera.mp4")
cap = cv2.VideoCapture("Teros_v1c4.mp4")
#necesita resize, mas abajo en captura

# ===== CAMARA =====
#cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
#cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

#cap.set(cv2.CAP_PROP_FPS, 5)  #limite de capturas -> FPS, NO FUNCA
#cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
#cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
#cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

# ===== VARIABLES =====
prev_time = 0
fps_list = []
fpsmod_list = []
latency_list = []

start_time = time.time()

while True:
    # ===== CONTROL DE TIEMPO =====
    elapsed = time.time() - start_time
    if elapsed > DURACION_SEGUNDOS:
        break

    # ===== CAPTURA =====
    ret, frame = cap.read()
    if not ret:
        break

    # ===== PREPROCESAMIENTO =====
    frame = cv2.resize(frame, (640, 480))
    #frame = cv2.resize(frame, (416, 256))
    #frame = cv2.resize(frame, (320, 192))
    #frame = cv2.resize(frame, (320, 240))
    #frame = cv2.resize(frame, (256, 160))

    # ===== INFERENCIA =====
    t1 = time.time()
    results = model(frame,
    device="cpu",
    conf=0.3,
    iou=0.5,
    classes=[0, 2, 5, 7],
    verbose=False)
    t2 = time.time()
    #0: persona, 2:car 3:moto 5:bus 7:truck
    
    fps_modelo = 1/(t2 - t1)
    latency_mod = t2-t1
    
    # ===== DIBUJO =====
    dibujar_detecciones(frame, results)

    # ===== FPS =====
    curr_time = time.time()
    fps = 1 / (curr_time - prev_time) if prev_time != 0 else 0
    prev_time = curr_time

    # Guardar FPS (evitamos el primer valor que suele ser inestable)
    if elapsed > 3:  #yolov8 640x640 es 2, en 320x es 3
        fps_list.append(fps)
        fpsmod_list.append(fps_modelo)
        latency_list.append(latency_mod)

    # ===== VISUALIZACION y FPS =====
    mostrar_frame(frame, fps)

    if cv2.waitKey(1) == 27:
        break

# ===== RESULTADOS =====
#liberacion de recursos
cap.release()
cv2.destroyAllWindows()

# Metricas
if len(fps_list) > 0:
    avg_fps = sum(fps_list) / len(fps_list)
    min_fps = min(fps_list)
    max_fps = max(fps_list)

    avg_fpsmod = sum(fpsmod_list) / len(fpsmod_list)
    avg_latency = sum(latency_list) / len(latency_list)

    print("\n===== DEBUG =====")
    print(f"fps lista: {fps_list}")
    print(f"fpsMOD lista: {fpsmod_list}")
    
    print("\n===== RESULTADOS =====")
    print(f"Duracion del video: {DURACION_SEGUNDOS} s")
    print(f"Frames medidos: {len(fps_list)}")
    print(f"FPS promedio: {avg_fps:.2f}")
    print(f"FPS minimo:   {min_fps:.2f}")
    print(f"FPS maximo:   {max_fps:.2f}\n")
    
    print(f"Latencia YOLO promedio: {avg_latency*1000:.2f} ms/img")
    print(f"FPS YOLO promedio: {avg_fpsmod:.2f}")
else:
    print("No se pudieron medir FPS.")
