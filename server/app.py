from flask import Flask, request, jsonify, session
from flask_bcrypt import Bcrypt
from flask_session import Session
from uuid import uuid4
from flask_cors import CORS
from config import ApplicationConfig
from models import db, User, Container
import docker
from sqlalchemy import asc, desc
import random
import tarfile
from io import BytesIO
from os import environ
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
allowed_origins = environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
CORS(app, origins=allowed_origins, supports_credentials=True)


@app.before_request
def start_timer():
    request._start_time = time.time()


@app.after_request
def log_request(response):
    duration = round((time.time() - request._start_time) * 1000, 2)
    logger.info(
        "%s %s %s %sms user=%s",
        request.method,
        request.path,
        response.status_code,
        duration,
        session.get("user_id", "anonymous")
    )
    return response
bcrypt = Bcrypt(app)

app.config.from_object(ApplicationConfig)
db.init_app(app)
with app.app_context():
    db.create_all()

Session(app)

try:
    docker_client = docker.from_env()
except Exception:
    docker_client = None


@app.route("/health", methods=["GET"])
def health():
    checks = {
        "redis": False,
        "database": False,
        "docker": docker_client is not None
    }
    try:
        from config import ApplicationConfig
        ApplicationConfig.SESSION_REDIS.ping()
        checks["redis"] = True
    except Exception:
        pass
    try:
        db.session.execute(db.text("SELECT 1"))
        checks["database"] = True
    except Exception:
        pass

    status = "ok" if all(checks.values()) else "degraded"
    return jsonify({"status": status, "checks": checks}), 200


@app.route("/register", methods=["POST"])
def register_user():
    email = request.json["email"]
    password = request.json["password"]

    user_exists = User.query.filter_by(email=email).first() is not None

    if user_exists:
        return jsonify({"error": "User already exists"}), 409

    user_id = str(uuid4())
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    new_user = User(id=user_id, email=email, password=hashed_password)

    db.session.add(new_user)
    db.session.commit()

    session["user_id"] = new_user.id
    session.modified = True

    return jsonify({
        "id": new_user.id,
        "email": new_user.email
    })


@app.route("/login", methods=["POST"])
def login_user():
    email = request.json["email"]
    password = request.json["password"]

    user = User.query.filter_by(email=email).first()

    if user is None:
        return jsonify({"error": "Unauthorized"}), 401

    if not bcrypt.check_password_hash(user.password, password):
        return jsonify({"error": "Unauthorized"}), 401 

    session["user_id"] = user.id
    session.modified = True

    return jsonify({
        "id": user.id,
        "email": user.email
    })
    

@app.route("/logout", methods=["DELETE"])
def logout_user():
    if "user_id" in session:
        session.pop("user_id")
        session.modified = True
        return "200"
    else:
        return jsonify({"error": "User not logged in"}), 401


@app.route("/@me", methods=['GET'])
def get_current_user():
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    user = User.query.filter_by(id=user_id).first()

    if user is None:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "id": user.id,
        "email": user.email
    })


@app.route("/containers", methods=["GET"])
def get_containers():
    try:
        current_user_id = session.get("user_id")
        if current_user_id is None:
            return jsonify({"error": "User not authenticated"}), 401

        search_term = request.args.get("search_term", "")
        sort_column = request.args.get("sort_column", "name")
        sort_order = request.args.get("sort_order", "asc") 

        containers_query = Container.query.filter_by(user_id=current_user_id)

        if search_term:
            containers_query = containers_query.filter(
                (Container.name.ilike(f"%{search_term}%")) | (Container.status.ilike(f"%{search_term}%"))
            )

        if sort_column in ["name", "status"]:
            if sort_order == "asc":
                containers_query = containers_query.order_by(asc(getattr(Container, sort_column)))
            else:
                containers_query = containers_query.order_by(desc(getattr(Container, sort_column)))

        containers = containers_query.all()

        container_data = []
        for container in containers:
            container_info = {
                "id": container.id,
                "name": container.name,
                "status": container.status
            }
            container_data.append(container_info)

        return jsonify(container_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

@app.route("/pull_container", methods=["POST"])
def create_container():
    current_user_id = session.get("user_id")
    if current_user_id is None:
        return jsonify({"error": "User not authenticated"}), 401

    image_name = request.json.get("image_name")

    try:
        try:
            docker_client.images.pull(image_name)
        except docker.errors.ImageNotFound:
            return jsonify({"error": "Image not found"}), 404

        host_port = random.randint(49152, 65535)
        port_bindings = {80: ('0.0.0.0', host_port)} 

        container = docker_client.containers.run(
            image_name,
            detach=True,
            ports=port_bindings
        )

        container_id = container.id
        container_name = container.name
        container_status = "running"

        current_user = User.query.get(current_user_id)
        new_container = Container(id=container_id, name=container_name, status=container_status, user=current_user)
        db.session.add(new_container)
        db.session.commit()

        return jsonify({"message": "Container created and started successfully", "container_id": container_id}), 201
    except docker.errors.APIError as e:
        return jsonify({"error": str(e)}), 500
    

@app.route("/stop_container", methods=["POST"])
def stop_container():
    container_id = request.json["container_id"]

    try:
        container = docker_client.containers.get(container_id)
        container.stop()
        
        updated_container = Container.query.filter_by(id=container_id).first()
        updated_container.status = "stopped"
        db.session.commit()
        
        return jsonify({"message": "Container stopped successfully"})
    except docker.errors.NotFound:
        return jsonify({"error": "Container not found"}), 404
    except docker.errors.APIError as e:
        return jsonify({"error": str(e)}), 500
    

@app.route("/start_container", methods=["POST"])
def start_container():
    container_id = request.json["container_id"]

    try:
        container = docker_client.containers.get(container_id)
        container.start()
        
        updated_container = Container.query.filter_by(id=container_id).first()
        updated_container.status = "running"
        db.session.commit()
        
        return jsonify({"message": "Container started successfully"})
    except docker.errors.NotFound:
        return jsonify({"error": "Container not found"}), 404
    except docker.errors.APIError as e:
        return jsonify({"error": str(e)}), 500
    

@app.route("/delete_container", methods=["DELETE"])
def delete_container():
    container_id = request.json["container_id"]

    try:
        container = docker_client.containers.get(container_id)
        
        if container.status == "running":
            container.stop()

        container.remove()

        deleted_container = Container.query.filter_by(id=container_id).first()
        db.session.delete(deleted_container)
        db.session.commit()

        return jsonify({"message": "Container deleted successfully"})
    except docker.errors.NotFound:
        return jsonify({"error": "Container not found"}), 404
    except docker.errors.APIError as e:
        return jsonify({"error": str(e)}), 500
    

@app.route("/container_details/<container_id>", methods=["GET"])
def get_container_details(container_id):
    try:
        container = docker_client.containers.get(container_id)
            
        container_details = {
            "id": container.id,
            "name": container.name,
            "status": container.status,
            "image": container.image.tags[0],
            "ports": container.attrs['HostConfig']['PortBindings'],
            "logs": container.logs().decode('utf-8')
        }
        return jsonify(container_details)
    except docker.errors.NotFound:
        return jsonify({"error": "Container not found"}), 404
    except docker.errors.APIError as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/build_and_push_image', methods=['POST'])
def build_and_push_image():
    repository = request.form.get('repository')
    tag = request.form.get('tag')
    username = request.form.get('username')
    password = request.form.get('password')
    dockerfile = request.files.get('dockerfile')
    # requirement = request.files.get('requirement')

    if not dockerfile:
        return jsonify({"error": "Dockerfile not provided"}), 400

    image_tag = f'{repository}:{tag}'

    try:
        tar_data = BytesIO()

        with tarfile.open(fileobj=tar_data, mode='w') as tar:
            tarinfo = tarfile.TarInfo('Dockerfile')
            dockerfile.seek(0)
            tarinfo.size = len(dockerfile.read())
            dockerfile.seek(0)
            tar.addfile(tarinfo, dockerfile)
        
        # if requirement:
        #         tarinfo_req = tarfile.TarInfo('requirements.txt')
        #         requirement.seek(0)
        #         tarinfo_req.size = len(requirement.read())
        #         requirement.seek(0)
        #         tar.addfile(tarinfo_req, requirement)

        tar_data.seek(0)

        for line in docker_client.images.build(fileobj=tar_data, tag=image_tag, custom_context=True):
            print(line)

        docker_client.login(username=username, password=password)

        for line in docker_client.images.push(repository, tag=tag, stream=True, decode=True):
            print(line)

        return jsonify({"message": f"Image {image_tag} pushed to Docker registry successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/users", methods=["GET"])
def get_all_users():
    try:
        users = User.query.all()
        user_data = []
        print(session)

        for user in users:
            user_info = {
                "id": user.id,
                "email": user.email,
            }
            user_data.append(user_info)

        return jsonify(user_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    




if __name__ == '__main__':
    app.run(port=5555, debug=True)