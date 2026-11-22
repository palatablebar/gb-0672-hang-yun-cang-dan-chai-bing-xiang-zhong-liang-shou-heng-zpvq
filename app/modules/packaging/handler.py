from fastapi import APIRouter, Request, Body
from app.engine import evaluate
from app.web import render
router=APIRouter()
@router.get('/packaging')
def page(request:Request):
    return render(request,'packaging')
@router.post('/api/packaging')
def calculate(payload:dict=Body(default={})):
    return evaluate(payload,until=2)
