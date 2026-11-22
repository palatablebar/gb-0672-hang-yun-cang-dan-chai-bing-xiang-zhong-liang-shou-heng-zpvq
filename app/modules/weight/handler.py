from fastapi import APIRouter, Request, Body
from app.engine import evaluate
from app.web import render
router=APIRouter()
@router.get('/weight')
def page(request:Request):
    return render(request,'weight')
@router.post('/api/weight')
def calculate(payload:dict=Body(default={})):
    return evaluate(payload,until=5)
