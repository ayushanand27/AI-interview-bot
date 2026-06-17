import requests
r = requests.post('http://127.0.0.1:8000/api/v1/interviews/sessions', json={
    'role_title':'Backend Dev', 'experience_level':'mid','topic_focus':'Python'
})
print(r.status_code)
print(r.text)
