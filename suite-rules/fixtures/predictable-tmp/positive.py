def save(data: bytes) -> str:
    path = "/tmp/render.png"
    with open(path, "wb") as f:
        f.write(data)
    return path
