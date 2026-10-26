"""Sign-in request and response bodies (BE-10)."""

from pydantic import BaseModel, Field


class RequestCodeIn(BaseModel):
    email: str = Field(max_length=254)


class VerifyCodeIn(BaseModel):
    email: str = Field(max_length=254)
    code: str = Field(pattern=r"^[0-9]{6}$")
    next: str | None = Field(default=None, max_length=2000)


class VerifyCodeOut(BaseModel):
    redirect: str


class AuthProvidersOut(BaseModel):
    google: bool
