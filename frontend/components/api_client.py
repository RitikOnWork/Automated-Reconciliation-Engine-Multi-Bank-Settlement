import os
import streamlit as st
import requests
from dotenv import load_dotenv

load_dotenv()

# Fallback URL matching docker network contexts
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000/api/v1")


class APIClient:
    @staticmethod
    def _get_headers() -> dict:
        """
        Builds authorization headers if a JWT access token exists in session.
        """
        headers = {}
        if "access_token" in st.session_state and st.session_state["access_token"]:
            headers["Authorization"] = f"Bearer {st.session_state['access_token']}"
        return headers

    @classmethod
    def post(cls, path: str, json_data: dict = None, data: dict = None, files: dict = None) -> tuple:
        """
        Executes an authorized HTTP POST call.
        """
        url = f"{BACKEND_API_URL}/{path.lstrip('/')}"
        try:
            response = requests.post(
                url, 
                json=json_data, 
                data=data, 
                files=files, 
                headers=cls._get_headers()
            )
            return response.status_code, response.json()
        except Exception as e:
            return 500, {"success": False, "error": {"message": f"Connection Error: {str(e)}"}}

    @classmethod
    def get(cls, path: str, params: dict = None) -> tuple:
        """
        Executes an authorized HTTP GET call.
        """
        url = f"{BACKEND_API_URL}/{path.lstrip('/')}"
        try:
            response = requests.get(
                url, 
                params=params, 
                headers=cls._get_headers()
            )
            return response.status_code, response.json()
        except Exception as e:
            return 500, {"success": False, "error": {"message": f"Connection Error: {str(e)}"}}

    @classmethod
    def put(cls, path: str, json_data: dict = None) -> tuple:
        """
        Executes an authorized HTTP PUT call.
        """
        url = f"{BACKEND_API_URL}/{path.lstrip('/')}"
        try:
            response = requests.put(
                url, 
                json=json_data, 
                headers=cls._get_headers()
            )
            return response.status_code, response.json()
        except Exception as e:
            return 500, {"success": False, "error": {"message": f"Connection Error: {str(e)}"}}

    @classmethod
    def login(cls, username: str, password: str) -> bool:
        """
        Exchanges credentials for JWT token and stores token in session state.
        """
        status_code, data = cls.post(
            "/auth/token",
            data={"username": username, "password": password}
        )
        if status_code == 200 and "access_token" in data:
            st.session_state["access_token"] = data["access_token"]
            st.session_state["username"] = username
            return True
        return False

    @classmethod
    def register(cls, username: str, password: str, role: str = "analyst") -> bool:
        """
        Registers a new user record through the backend.
        """
        status_code, data = cls.post(
            "/auth/register",
            json_data={"username": username, "password": password, "role": role}
        )
        return status_code == 201
