// ---------------------------------------------
// ESTADO
// ---------------------------------------------

const MODOS = {
    roi:             { color: "#33ff66", titulo: "ROI",                  tipo: "rect",  maxClicks: 2 },
    linea_personas:  { color: "#4488ff", titulo: "Linea 1 - Personas",  tipo: "linea", maxClicks: 3 },
    linea_vehiculos: { color: "#ff3333", titulo: "Linea 2 - Vehiculos", tipo: "linea", maxClicks: 3 }
};

let puntos     = [];
let modoActual = null;

// ---------------------------------------------
// SELECTOR DE MODO
// ---------------------------------------------

function seleccionarModo(modo) {
    // Validar que el ROI este configurado antes de lineas
    if (modo !== "roi") {
        const configActual = window._configCache;
        if (!configActual || !configActual.roi || !configActual.roi.p1) {
            mostrarMensaje("Primero debes configurar el ROI.", "error");
            return;
        }
    }

    modoActual = modo;
    puntos     = [];
    limpiarCanvas();

    document.querySelectorAll(".btn-modo").forEach(b => b.classList.remove("activo"));
    const ids = {
        roi:             "btn-modo-roi",
        linea_personas:  "btn-modo-per",
        linea_vehiculos: "btn-modo-veh"
    };
    document.getElementById(ids[modo]).classList.add("activo");

    document.getElementById("acciones-modo").classList.remove("oculto");

    const info   = MODOS[modo];
    document.getElementById("paso-titulo").textContent = info.titulo;
    const instrMsg = info.tipo === "rect"
        ? "Haz 2 clicks para definir las esquinas opuestas del ROI."
        : `Haz 3 clicks: p1, p2 (linea) y p3 (zona positiva). Deben estar dentro del ROI.`;
    document.getElementById("instruccion").textContent = instrMsg;

    // Dibujar ROI de referencia si ya esta guardado y no estamos en modo ROI
    if (modo !== "roi") {
        dibujarROIReferencia();
    }
}

// ---------------------------------------------
// CAMARA
// ---------------------------------------------

function actualizarFoto() {
    document.getElementById("camara-img").src = "/frame?t=" + Date.now();
    puntos = [];
    limpiarCanvas();
}

// ---------------------------------------------
// CLICKS EN LA IMAGEN
// ---------------------------------------------

function onClickImagen(event) {
    if (!modoActual) {
        mostrarMensaje("Selecciona un modo primero (Linea 1, Linea 2 o ROI).", "error");
        return;
    }

    const maxClicks = MODOS[modoActual].maxClicks;

    if (puntos.length >= maxClicks) {
        mostrarMensaje("Ya tienes todos los puntos. Guarda o resetea antes de continuar.", "error");
        return;
    }

    const img  = document.getElementById("camara-img");
    const rect = img.getBoundingClientRect();

    const clickX = event.clientX - rect.left;
    const clickY = event.clientY - rect.top;

    const escalaX = img.naturalWidth  / rect.width;
    const escalaY = img.naturalHeight / rect.height;
    const realX   = Math.round(clickX * escalaX);
    const realY   = Math.round(clickY * escalaY);

    puntos.push({ x: realX, y: realY, sx: clickX, sy: clickY });
    dibujarEstado();

    // Mensaje dinamico segun cuantos clicks faltan
    const restantes = maxClicks - puntos.length;
    if (restantes > 0) {
        mostrarMensaje(`Punto ${puntos.length} registrado. Faltan ${restantes} clicks.`, "ok");
    } else {
        mostrarMensaje("Listo. Presiona Guardar para confirmar.", "ok");
    }
}

// ---------------------------------------------
// CANVAS
// ---------------------------------------------

function limpiarCanvas() {
    const canvas = document.getElementById("overlay");
    const ctx    = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
}

function sincronizarCanvas() {
    const img    = document.getElementById("camara-img");
    const canvas = document.getElementById("overlay");
    canvas.width  = img.clientWidth;
    canvas.height = img.clientHeight;
}

function dibujarEstado() {
    sincronizarCanvas();
    limpiarCanvas();

    const canvas = document.getElementById("overlay");
    const ctx    = canvas.getContext("2d");
    const color  = modoActual ? MODOS[modoActual].color : "#ffffff";
    const tipo   = modoActual ? MODOS[modoActual].tipo  : "linea";

    // Dibujar ROI de referencia primero (fondo) si no estamos en modo ROI
    if (modoActual !== "roi") {
        dibujarROIReferencia(ctx);
    }

    // Dibujar p1 y p2 en verde
    puntos.slice(0, 2).forEach(p => {
        ctx.beginPath();
        ctx.arc(p.sx, p.sy, 6, 0, Math.PI * 2);
        ctx.fillStyle = "#00ff00";
        ctx.fill();
    });

    // Linea o rectangulo
    if (puntos.length >= 2) {
        ctx.strokeStyle = color;
        ctx.lineWidth   = 2;

        if (tipo === "rect") {
            const x = Math.min(puntos[0].sx, puntos[1].sx);
            const y = Math.min(puntos[0].sy, puntos[1].sy);
            const w = Math.abs(puntos[1].sx - puntos[0].sx);
            const h = Math.abs(puntos[1].sy - puntos[0].sy);
            ctx.strokeRect(x, y, w, h);
        } else {
            ctx.beginPath();
            ctx.moveTo(puntos[0].sx, puntos[0].sy);
            ctx.lineTo(puntos[1].sx, puntos[1].sy);
            ctx.stroke();
        }
    }

    // p3 circulo amarillo con +
    if (puntos.length === 3) {
        const p = puntos[2];
        ctx.beginPath();
        ctx.arc(p.sx, p.sy, 8, 0, Math.PI * 2);
        ctx.fillStyle   = "#ffff00";
        ctx.fill();
        ctx.strokeStyle = "#000";
        ctx.lineWidth   = 1.5;
        ctx.stroke();

        ctx.beginPath();
        ctx.moveTo(p.sx,     p.sy - 5);
        ctx.lineTo(p.sx,     p.sy + 5);
        ctx.moveTo(p.sx - 5, p.sy);
        ctx.lineTo(p.sx + 5, p.sy);
        ctx.strokeStyle = "#000";
        ctx.lineWidth   = 1.5;
        ctx.stroke();
    }
}

// Dibuja el ROI guardado como referencia visual
function dibujarROIReferencia(ctx) {
    const config = window._configCache;
    if (!config || !config.roi || !config.roi.p1 || !config.roi.p2) return;

    const img    = document.getElementById("camara-img");
    const rect   = img.getBoundingClientRect();
    const escalaX = rect.width  / img.naturalWidth;
    const escalaY = rect.height / img.naturalHeight;

    // Convertir coordenadas reales a coordenadas de pantalla
    const p1 = config.roi.p1;
    const p2 = config.roi.p2;
    const sx1 = p1[0] * escalaX;
    const sy1 = p1[1] * escalaY;
    const sx2 = p2[0] * escalaX;
    const sy2 = p2[1] * escalaY;

    if (!ctx) {
        // Si no se paso ctx, obtenerlo del canvas
        sincronizarCanvas();
        const canvas = document.getElementById("overlay");
        ctx = canvas.getContext("2d");
    }

    const x = Math.min(sx1, sx2);
    const y = Math.min(sy1, sy2);
    const w = Math.abs(sx2 - sx1);
    const h = Math.abs(sy2 - sy1);

    // Rectangulo semitransparente verde
    ctx.strokeStyle = "#33ff66";
    ctx.lineWidth   = 2;
    ctx.setLineDash([6, 3]);  // linea punteada para distinguirlo de la linea de conteo
    ctx.strokeRect(x, y, w, h);
    ctx.setLineDash([]);      // resetear linea punteada
}

// ---------------------------------------------
// AVANZADO / RED
// ---------------------------------------------

function toggleAvanzado() {
    const panel  = document.getElementById("panel-avanzado");
    const btn    = document.querySelector(".btn-colapsar");
    const oculto = panel.classList.toggle("oculto");
    btn.textContent = (oculto ? "\u25bc" : "\u25b2") + " Avanzado / Red";
}

async function guardarRed() {
    const ssid     = document.getElementById("wifi-ssid").value.trim();
    const password = document.getElementById("wifi-password").value;

    if (!ssid) {
        mostrarMensaje("El SSID no puede estar vacio.", "error");
        return;
    }
    if (password.length < 8) {
        mostrarMensaje("La contrasena debe tener al menos 8 caracteres.", "error");
        return;
    }

    await postConfig("red", { ssid, password });
    mostrarMensaje("Configuracion de red guardada. Aplicara al finalizar.", "ok");
}

// ---------------------------------------------
// AFORO
// ---------------------------------------------

async function guardarAforo() {
    const maxPer  = parseInt(document.getElementById("max-personas").value);
    const maxVeh  = parseInt(document.getElementById("max-vehiculos").value);
    const offPer  = parseInt(document.getElementById("offset-personas").value);
    const offVeh  = parseInt(document.getElementById("offset-vehiculos").value);

    // Validacion basica
    if (isNaN(maxPer) || isNaN(maxVeh) || isNaN(offPer) || isNaN(offVeh)) {
        mostrarMensaje("Todos los valores deben ser numeros.", "error");
        return;
    }
    if (maxPer < 0 || maxVeh < 0 || offPer < 0 || offVeh < 0) {
        mostrarMensaje("Los valores no pueden ser negativos.", "error");
        return;
    }

    await postConfig("aforo", {
        max_personas:     maxPer,
        max_vehiculos:    maxVeh,
        offset_personas:  offPer,
        offset_vehiculos: offVeh
    });
}

// ---------------------------------------------
// GUARDAR
// ---------------------------------------------

async function guardarModoActual() {
    if (!modoActual) return;

    const maxClicks = MODOS[modoActual].maxClicks;

    if (puntos.length < maxClicks) {
        mostrarMensaje(`Faltan ${maxClicks - puntos.length} puntos para guardar.`, "error");
        return;
    }

    // Validacion ROI
    if (MODOS[modoActual].tipo === "rect") {
        const dx   = Math.abs(puntos[1].x - puntos[0].x);
        const dy   = Math.abs(puntos[1].y - puntos[0].y);
        const area = dx * dy;

        if (dx === 0) { mostrarMensaje("El ROI no tiene ancho.", "error"); return; }
        if (dy === 0) { mostrarMensaje("El ROI no tiene alto.", "error");  return; }
        if (area < 1000) { mostrarMensaje(`ROI muy pequeno (${area}px). Aleja mas los puntos.`, "error"); return; }
    }

    // Validacion puntos dentro del ROI para lineas
    if (MODOS[modoActual].tipo === "linea") {
        const roi = window._configCache && window._configCache.roi;
        if (roi && roi.p1 && roi.p2) {
            const roiX1 = Math.min(roi.p1[0], roi.p2[0]);
            const roiY1 = Math.min(roi.p1[1], roi.p2[1]);
            const roiX2 = Math.max(roi.p1[0], roi.p2[0]);
            const roiY2 = Math.max(roi.p1[1], roi.p2[1]);

            for (let i = 0; i < puntos.length; i++) {
                const p = puntos[i];
                if (p.x < roiX1 || p.x > roiX2 || p.y < roiY1 || p.y > roiY2) {
                    mostrarMensaje(`El punto ${i + 1} esta fuera del ROI. Reintenta.`, "error");
                    puntos = [];
                    limpiarCanvas();
                    if (modoActual !== "roi") dibujarROIReferencia();
                    return;
                }
            }
        }
    }

    const valor = {
        p1: [puntos[0].x, puntos[0].y],
        p2: [puntos[1].x, puntos[1].y]
    };

    if (maxClicks === 3) {
        valor.p3 = [puntos[2].x, puntos[2].y];
    }

    await postConfig(modoActual, valor);
    puntos = [];
    limpiarCanvas();

    // Redibujar ROI de referencia si corresponde
    if (modoActual !== "roi") dibujarROIReferencia();
}

async function postConfig(clave, valor) {
    const res  = await fetch("/config/set", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ clave, valor })
    });
    const data = await res.json();
    if (data.ok) {
        mostrarMensaje(`'${clave}' guardado correctamente.`, "ok");
        actualizarTabla();
    } else {
        mostrarMensaje(data.error || "Error al guardar.", "error");
    }
}

// ---------------------------------------------
// RESETEAR
// ---------------------------------------------

async function resetearModoActual() {
    if (!modoActual) return;
    await resetearClave(modoActual);
}

async function resetearClave(clave) {
    const res  = await fetch("/config/reset", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ clave })
    });
    const data = await res.json();
    if (data.ok) {
        mostrarMensaje(`'${clave}' reseteado.`, "ok");
        actualizarTabla();
        puntos = [];
        limpiarCanvas();
    }
}

async function resetearTodo() {
    if (!confirm("Resetear toda la configuracion al template por defecto?")) return;
    const res  = await fetch("/config/reset", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ todo: true })
    });
    const data = await res.json();
    if (data.ok) {
        mostrarMensaje("Configuracion reseteada.", "ok");
        actualizarTabla();
        puntos = [];
        limpiarCanvas();
    }
}

// ---------------------------------------------
// FINALIZAR
// ---------------------------------------------

async function finalizar() {
    if (!confirm("Finalizar configuracion y cerrar el servidor?")) return;

    const res  = await fetch("/finalizar", { method: "POST" });
    const data = await res.json();

    if (data.ok) {
        mostrarMensaje("Configuracion finalizada. Cerrando servidor...", "ok");
        setTimeout(() => {
            document.body.innerHTML = `
                <div style="text-align:center;margin-top:100px;color:#fff">
                    <h2>Configuracion completada.</h2>
                    <p style="margin-top:12px;color:#aaa">Puedes cerrar esta pagina.</p>
                </div>`;
        }, 1500);
    } else {
        mostrarMensaje(data.error, "error");
    }
}

// ---------------------------------------------
// TABLA CONFIG
// ---------------------------------------------

async function actualizarTabla() {
    const res    = await fetch("/config");
    const config = await res.json();

    // Guardar en cache global para usarla en validaciones y dibujo del ROI
    window._configCache = config;
    // Rellenar inputs de aforo con valores del config
    if (config.aforo) {
        const a = config.aforo;
        if (a.max_personas     !== null) document.getElementById("max-personas").value    = a.max_personas;
        if (a.max_vehiculos    !== null) document.getElementById("max-vehiculos").value   = a.max_vehiculos;
        if (a.offset_personas  !== null) document.getElementById("offset-personas").value = a.offset_personas;
        if (a.offset_vehiculos !== null) document.getElementById("offset-vehiculos").value = a.offset_vehiculos;
    }
    
    // Rellenar inputs de red   
    if (config.red) {
        const r = config.red;
        if (r.ssid)     document.getElementById("wifi-ssid").value     = r.ssid;
        if (r.password) document.getElementById("wifi-password").value = r.password;
    }
    
    //Tabla
    const div = document.getElementById("tabla-config");
    let html  = "<table class='tabla'>";

    for (const [clave, valor] of Object.entries(config)) {
        const esNull = valor === null ||
            (typeof valor === "object" && valor !== null &&
             Object.values(valor).every(v => v === null));

        const claseValor = esNull ? "valor-null" : "valor-ok";
        const textoValor = esNull ? "sin configurar" : JSON.stringify(valor);

        html += `<tr>
                    <td>${clave}</td>
                    <td class="${claseValor}">${textoValor}</td>
                 </tr>`;
    }

    html += "</table>";
    div.innerHTML = html;
}

// ---------------------------------------------
// MENSAJES
// ---------------------------------------------

function mostrarMensaje(texto, tipo = "ok") {
    const el = document.getElementById("mensaje");
    el.textContent   = texto;
    el.className     = `mensaje ${tipo}`;
    el.style.display = "block";
    setTimeout(() => { el.style.display = "none"; }, 3000);
}

// ---------------------------------------------
// INICIO
// ---------------------------------------------

window.onload = () => {
    actualizarTabla();
};
