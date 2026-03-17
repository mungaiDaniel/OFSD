class HttpError(Exception):
    """Bad Request"""
    error_code = "Bad Request"
    status_code = 400


class DatabaseError(HttpError):
    error_code = "Database Error"
    status_code = 500


