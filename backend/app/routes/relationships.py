"""Authenticated relationship lifecycle; physical names never come from requests."""
import hashlib
import json
from typing import List, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.services.auth_service import get_current_user_id
from app.services import relationship_service as service
from app.models.relationship import DatasetRelationship

router = APIRouter(prefix='/api/relationships', tags=['Relationships'])
class Key(BaseModel):
    left: str
    right: str
class RelationshipRequest(BaseModel):
    name: str = Field(default='Approved relationship', max_length=150)
    left_dataset_id: str
    right_dataset_id: str
    keys: List[Key] = Field(min_length=1, max_length=8)
    join_type: Literal['INNER', 'LEFT'] = 'INNER'
    approved: bool = False
    active: bool = True
    preview_digest: str = ''

def preview(owner, req):
    data = req.model_dump()
    with service.SessionLocal() as db:
        left = service.owned(db, req.left_dataset_id, owner)
        right = service.owned(db, req.right_dataset_id, owner)
        measured = service.profile(left.physical_name, right.physical_name, data['keys'], req.join_type)
        versions = {d.id: [d.revision, service.fingerprint(d.physical_name)] for d in (left,right)}
    stable = {k:v for k,v in measured.items() if k != 'measured_at'}
    digest = hashlib.sha256(json.dumps([owner, req.left_dataset_id, req.right_dataset_id, data['keys'], req.join_type, versions, stable], sort_keys=True).encode()).hexdigest()
    return dict(profile=measured, preview_digest=digest)

def failure(exc):
    raise HTTPException(status_code=400, detail=str(exc))

@router.get('/datasets')
def datasets(owner: str = Depends(get_current_user_id)):
    return {'datasets': service.catalog(owner)}

@router.get('')
def listing(owner: str = Depends(get_current_user_id)):
    service.catalog(owner)
    return {'relationships': service.relationships(owner)}

@router.post('/preview')
def inspect_relationship(req: RelationshipRequest, owner: str = Depends(get_current_user_id)):
    try: return preview(owner, req)
    except service.RelationshipError as exc: failure(exc)

@router.get('/suggestions')
def suggestions(left_dataset_id: str, right_dataset_id: str, owner: str = Depends(get_current_user_id)):
    try:
        with service.SessionLocal() as db:
            left = service.owned(db, left_dataset_id, owner)
            right = service.owned(db, right_dataset_id, owner)
            candidates = []
            for a in service.schema(left.physical_name):
                for b in service.schema(right.physical_name):
                    if a['name'].lower() == b['name'].lower() and service.family(a['type']) == service.family(b['type']):
                        keys = [{'left': a['name'], 'right': b['name']}]
                        candidates.append(dict(keys=keys, profile=service.profile(left.physical_name, right.physical_name, keys), reason='Matching names and compatible types; measured candidate, not a database foreign key.'))
                        if len(candidates) == 8: return {'suggestions': candidates}
            return {'suggestions': candidates}
    except service.RelationshipError as exc: failure(exc)

@router.post('')
def create(req: RelationshipRequest, owner: str = Depends(get_current_user_id)):
    try:
        if preview(owner, req)['preview_digest'] != req.preview_digest:
            raise service.RelationshipError('Preview has changed or is missing. Inspect and approve the current profile.')
        return service.save(owner, req.model_dump())
    except service.RelationshipError as exc: failure(exc)

@router.put('/{relationship_id}')
def edit(relationship_id: str, req: RelationshipRequest, owner: str = Depends(get_current_user_id)):
    try:
        if preview(owner, req)['preview_digest'] != req.preview_digest:
            raise service.RelationshipError('Preview has changed or is missing. Inspect and approve the current profile.')
        return service.save(owner, req.model_dump(), relationship_id)
    except service.RelationshipError as exc: failure(exc)

@router.post('/{relationship_id}/deactivate')
def deactivate(relationship_id: str, owner: str = Depends(get_current_user_id)):
    with service.SessionLocal() as db:
        item = db.query(DatasetRelationship).filter_by(id=relationship_id, owner_id=owner).first()
        if not item: raise HTTPException(status_code=404, detail='Relationship not found or access denied.')
        item.active = False
        item.updated_at = service.get_ist_time()
        db.commit()
    return {'success': True}
