from ..models import Audit
def log(s,u,action,d=None,old=None,new=None): s.add(Audit(document_id=d.id if d else None,actor=u.username,role=u.role,action=action,old_value=old,new_value=new))
