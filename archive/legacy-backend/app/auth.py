from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session
from .database import db
from .models import User
def actor(authorization: str|None=Header(default=None), s:Session=Depends(db)):
    if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'Authentication required')
    u=s.query(User).filter_by(username=authorization[7:]).first()
    if not u: raise HTTPException(401,'Invalid session')
    return u
def role(required):
    def f(u=Depends(actor)):
        if u.role!=required: raise HTTPException(403,'Role not authorized')
        return u
    return f
