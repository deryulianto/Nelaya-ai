import xarray as xr
import numpy as np

def load_current_generic(file_path):
    ds = xr.open_dataset(file_path)

    # --- DETEKSI NAMA VARIABEL ---
    if "uo" in ds and "vo" in ds:
        u = ds["uo"]
        v = ds["vo"]
    elif "u_current" in ds and "v_current" in ds:
        u = ds["u_current"]
        v = ds["v_current"]
    else:
        raise ValueError("Variabel arus tidak dikenali (uo/vo atau u_current/v_current tidak ditemukan)")

    # --- HANDLE DIMENSI ---
    # Ambil permukaan jika ada depth
    if "depth" in u.dims:
        u = u.isel(depth=0)
        v = v.isel(depth=0)

    # Ambil waktu terakhir jika ada time
    if "time" in u.dims:
        u = u.isel(time=-1)
        v = v.isel(time=-1)

    # --- HITUNG SPEED ---
    speed = np.sqrt(u**2 + v**2)

    # --- MEAN AREA ACEH ---
    return {
        "current_ms": float(speed.mean().values),
        "current_u_ms": float(u.mean().values),
        "current_v_ms": float(v.mean().values),
    }
