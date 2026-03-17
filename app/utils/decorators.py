import functools
import logging
from flask_jwt_extended import verify_jwt_in_request, get_jwt
import app.utils.responses as error
from flask import request

def permission(arg):
    def check_permissions(f):
        
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            
            auth = request.authorization
            
            if auth is None and 'Authorization' in request.headers:
                try:
                    
                    verify_jwt_in_request()
                    claims = get_jwt()
                    
                    if claims['admin'] < arg:
                        
                        return error.NOT_ADMIN
                except ValueError:
                    
                    return error.HEADER_NOT_FOUND
                
                except Exception as why:
                    logging.error(why)
                    
                    return error.INVALID_INPUT_422
            
            return f(*args, **kwargs)
        
        return decorated
    
    return check_permissions