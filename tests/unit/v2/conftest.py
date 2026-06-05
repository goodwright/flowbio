import httpx

DEFAULT_BASE_URL = "https://app.flow.bio/api"


def parse_multipart(request: httpx.Request) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
    """Parse a multipart request into form fields and file parts.

    Returns ``(fields, files)`` where ``fields`` maps field name to its
    decoded string value and ``files`` maps field name to ``(filename, bytes)``.
    """
    boundary = request.headers["content-type"].split("boundary=")[1].encode()
    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes]] = {}
    for part in request.content.split(b"--" + boundary):
        if not part or part.startswith(b"--"):
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        header_blob, _, body = part.partition(b"\r\n\r\n")
        disposition = next(
            line for line in header_blob.decode().split("\r\n")
            if line.lower().startswith("content-disposition")
        )
        name = _disposition_param(disposition, "name")
        filename = _disposition_param(disposition, "filename")
        if filename is not None:
            files[name] = (filename, body)
        else:
            fields[name] = body.decode()
    return fields, files


def _disposition_param(disposition: str, key: str) -> str | None:
    marker = f'{key}="'
    if marker not in disposition:
        return None
    start = disposition.index(marker) + len(marker)
    end = disposition.index('"', start)
    return disposition[start:end]
