from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status

from app.core.security import verify_internal_api_key


@pytest.mark.asyncio
async def test_internal_api_key_logic():
    # Mock settings.ENVIRONMENT and settings.INTERNAL_API_KEY
    with patch("app.core.security.settings") as mock_settings:
        # Case 1: Key missing in non-dev env -> 401
        mock_settings.ENVIRONMENT = "production"
        mock_settings.INTERNAL_API_KEY = None

        with pytest.raises(HTTPException) as exc:
            await verify_internal_api_key(x_internal_api_key="something")
        assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED

        # Case 2: Key missing in dev env -> Allow
        mock_settings.ENVIRONMENT = "development"
        mock_settings.INTERNAL_API_KEY = None
        result = await verify_internal_api_key(x_internal_api_key=None)
        assert result is True

        # Case 3: Key set, but missing in request -> 403
        mock_settings.ENVIRONMENT = "production"
        mock_settings.INTERNAL_API_KEY = "secret"
        with pytest.raises(HTTPException) as exc:
            await verify_internal_api_key(x_internal_api_key=None)
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN

        # Case 4: Key set, wrong in request -> 403
        with pytest.raises(HTTPException) as exc:
            await verify_internal_api_key(x_internal_api_key="wrong")
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN

        # Case 5: Key set, correct in request -> True
        result = await verify_internal_api_key(x_internal_api_key="secret")
        assert result is True
