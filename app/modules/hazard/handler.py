from fastapi import APIRouter, Request, Body
from app.engine import evaluate
from app.web import render
router=APIRouter()
@router.get('/hazard')
def page(request:Request):
    return render(request,'hazard')
@router.post('/api/hazard')
def calculate(payload:dict=Body(default={})):
    return evaluate(payload,until=4)
