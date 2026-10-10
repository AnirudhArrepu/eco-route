import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from app.config import settings


def _client():
    if not settings.cognito_user_pool_id or not settings.cognito_app_client_id:
        raise HTTPException(503, "Cognito authentication is not configured")
    return boto3.client("cognito-idp", region_name=settings.aws_region)


def _call(operation, **kwargs):
    try:
        return operation(**kwargs)
    except ClientError as exc:
        error = exc.response.get("Error", {})
        code = error.get("Code", "CognitoError")
        status = 429 if code in {"TooManyRequestsException", "LimitExceededException"} else 400
        if code in {"InternalErrorException", "ServiceUnavailableException"}:
            status = 503
        raise HTTPException(status, error.get("Message", "Cognito request failed")) from exc
    except BotoCoreError as exc:
        raise HTTPException(503, "Cognito service is unavailable") from exc


def sign_up(email: str, password: str) -> dict:
    response = _call(
        _client().sign_up,
        ClientId=settings.cognito_app_client_id,
        Username=email.strip().lower(),
        Password=password,
        UserAttributes=[{"Name": "email", "Value": email.strip().lower()}],
    )
    return {
        "user_id": response.get("UserSub"),
        "confirmation_required": not response.get("UserConfirmed", False),
        "delivery": response.get("CodeDeliveryDetails"),
    }


def confirm_sign_up(email: str, code: str) -> dict:
    _call(
        _client().confirm_sign_up,
        ClientId=settings.cognito_app_client_id,
        Username=email.strip().lower(),
        ConfirmationCode=code.strip(),
    )
    return {"confirmed": True}


def resend_confirmation(email: str) -> dict:
    response = _call(
        _client().resend_confirmation_code,
        ClientId=settings.cognito_app_client_id,
        Username=email.strip().lower(),
    )
    return {"delivery": response.get("CodeDeliveryDetails")}


def _token_response(authentication: dict) -> dict:
    return {
        "access_token": authentication.get("AccessToken"),
        "id_token": authentication.get("IdToken"),
        "refresh_token": authentication.get("RefreshToken"),
        "expires_in": authentication.get("ExpiresIn"),
        "token_type": authentication.get("TokenType", "Bearer"),
    }


def log_in(email: str, password: str) -> dict:
    response = _call(
        _client().initiate_auth,
        ClientId=settings.cognito_app_client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email.strip().lower(), "PASSWORD": password},
    )
    if response.get("ChallengeName"):
        raise HTTPException(400, f"Additional sign-in challenge required: {response['ChallengeName']}")
    return _token_response(response.get("AuthenticationResult", {}))


def refresh(refresh_token: str) -> dict:
    response = _call(
        _client().initiate_auth,
        ClientId=settings.cognito_app_client_id,
        AuthFlow="REFRESH_TOKEN_AUTH",
        AuthParameters={"REFRESH_TOKEN": refresh_token},
    )
    if response.get("ChallengeName"):
        raise HTTPException(400, f"Additional sign-in challenge required: {response['ChallengeName']}")
    return _token_response(response.get("AuthenticationResult", {}))
