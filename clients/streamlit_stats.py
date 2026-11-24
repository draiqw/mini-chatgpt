"""Streamlit-клиент к настоящему mini-chatgpt, без копии серверной логики."""

import os

import requests
import streamlit as st

base_url = os.getenv("MINI_CHATGPT_URL", "http://localhost:18099").rstrip("/")

st.title("Статистика текста")
with st.form("stats"):
    message = st.text_area("Текст", max_chars=20_000)
    submitted = st.form_submit_button("Посчитать")

if submitted:
    try:
        response = requests.post(
            f"{base_url}/api/stats",
            json={"message": message},
            timeout=5,
        )
        response.raise_for_status()
        st.json(response.json())
    except requests.RequestException as error:
        st.error(f"Запрос не прошёл: {error}")
