import requests

API = "http://localhost/api" #Gateway :'v
token = None
rol = None
user = None

def login():
    global token, rol, user
    user = input("Usuario:")
    password = input("Contraseña:")
    resp = requests.post(f"{API}/auth/login",json={"user":user,"password":password})

    if resp.status_code ==200:
        data = resp.json()
        token = data["token"]
        rol = data["rol"]
        user = data["user"]
        print(f"Bienvenido a la plataforma {user} :D")
    else:
        print("No te mereces entrar a la plataforma :(", resp.text)

def opc1():
    print("Has seleccionado la opción 1")
def opc2():
    print("Has seleccionado la opción 2")      
def opc3():
    print("Has seleccionado la opción 3")   


def menu():
    while True:
        print("----------- Menú principal -----------")
        #Se definirán las opciones del menú según el rol
        if rol == "admin":
            # Opciones admin
            print("Eres admin owo")
        elif rol == "investigador":
            # Opciones investigador
            print("Eres investigador owo")
        elif rol == "usuario":
            # Opciones usuario
            print("Eres usuario owo")
        print("1. opc1")
        print("2. opc2")
        print("3. opc3")
        print("100000. Salir")
        opcion = input("Escoja una opción: ")

        if opcion == "1":
            opc1()  
        elif opcion == "2":
            opc2()
        elif opcion == "3":
            opc3()
        elif opcion == "100000":
            print("Saliendo...  *se crashea*")
            break
        else:
            print("Opción no válida")

if __name__ == "__main__":
    while True:
        print("----------- Proyecto Cloud -----------")
        opc = input("Escoja una opción: ")
        print("\nBienvenido owo")
        if opc == "1":
            login()
            if token:
                print("Correcto logueo")
                menu()
        elif opc == "2":
            break
        else:
            print("Opción no válida")