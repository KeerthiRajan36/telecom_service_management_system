from typing import Generic,Type,TypeVar, Any

from sqlalchemy.orm import Session, Query

ModelType = TypeVar("ModelType")

class BaseRepository(Generic[ModelType]):

    def __init__(self,model:Type[ModelType],db:Session):
        self.model = model
        self.db = db

    def base_query(self)-> Query:
        query = self.db.query(self.model)
        if hasattr(self.model,"is_deleted"):
            query = query.filter(self.model.is_deleted.is_(False))

        return query
    
    def get(self,id_:int)-> ModelType | None :
        return self.base_query().filter(self.model.id == id_).first()

    def get_all(self)-> list[ModelType]:
        return self.base_query().all()

    def create(self,obj_in:dict[str,Any])-> ModelType:
        obj=self.model(**obj_in)
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self,obj:ModelType,updates:dict[str,Any])-> ModelType:
        for field, value in updates.items():
            if value is not None:
                setattr(obj,field,value)
            self.db.commit()
            self.db.refresh(obj)
            return obj

    def delete(self,obj:ModelType,soft:bool=True)-> None:
        if soft and hasattr(obj,"is_deleted"):
            obj.is_deleted = True
            self.db.commit()
        else:
            self.db.delete(obj)
            self.db.commit()
            