import os
import random
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client

app = Flask(__name__)
CORS(app)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL et SUPABASE_KEY doivent être définis en variables d'environnement.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

TARIFS = {"simple": 30, "double": 50, "suite": 70}
TYPES_CHAMBRES = ["simple", "double", "suite"]
CHAMBRES = {
    "simple": [100 + i for i in range(1, 100)],
    "double": [200 + i for i in range(1, 100)],
    "suite":  [300 + i for i in range(1, 100)]
}

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_pin():
    return str(random.randint(1000, 9999))

def chambres_libres(start, end, exclude_id=None):
    start_obj = datetime.strptime(start, "%Y-%m-%d")
    end_obj   = datetime.strptime(end,   "%Y-%m-%d")

    query = supabase.table("reservations").select("*").neq("etat", "annule")
    if exclude_id is not None:
        query = query.neq("id", exclude_id)
    reservations = query.execute().data

    libres = {}
    for type_chambre, nums in CHAMBRES.items():
        libres[type_chambre] = []
        for num in nums:
            libre = True
            for r in reservations:
                if r["num_chambre"] == num and r["type_chambre"] == type_chambre:
                    if not r.get("datestart") or not r.get("dateend"):
                        continue
                    r_start = datetime.strptime(r["datestart"], "%Y-%m-%d")
                    r_end   = datetime.strptime(r["dateend"],   "%Y-%m-%d")
                    if not (end_obj <= r_start or start_obj >= r_end):
                        libre = False
                        break
            if libre:
                libres[type_chambre].append(num)
    return libres

def get_user_id(username):
    """Retourne l'id d'un utilisateur depuis son username."""
    result = supabase.table("users").select("id").eq("username", username).execute()
    return result.data[0]["id"] if result.data else None

def format_res(r):
    return {
        "id":           r["id"],
        "nom":          r["nom"],
        "prenom":       r["prenom"],
        "type_chambre": r["type_chambre"],
        "start":        r["datestart"],
        "end":          r["dateend"],
        "etat":         r["etat"],
        "num_chambre":  r["num_chambre"],
        "contact":      r["contact"],
        "pin_code":     r["pin_code"],
        "user_id":      r.get("user_id")
    }

# ── AUTH ──────────────────────────────────────────────────────────────────────

@app.route('/api/register', methods=['POST'])
def register():
    data     = request.json
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"success": False, "message": "Nom d'utilisateur et mot de passe requis."})
    # Vérification Python (rapide)
    existing = supabase.table("users").select("username").eq("username", username).execute()
    if existing.data:
        return jsonify({"success": False, "message": "Cet utilisateur existe déjà."})
    try:
        supabase.table("users").insert({
            "username":      username,
            "password_hash": hash_password(password),
            "full_name":     data.get("full_name", ""),
            "email":         data.get("email", ""),
            "phone":         data.get("phone", "")
        }).execute()
    except Exception:
        # Contrainte UNIQUE violée au niveau DB (double sécurité)
        return jsonify({"success": False, "message": "Cet utilisateur existe déjà."})
    return jsonify({"success": True, "message": "Inscription réussie."})


@app.route('/api/login', methods=['POST'])
def login():
    data     = request.json
    username = data.get('username')
    password = data.get('password')
    result   = supabase.table("users").select("*").eq("username", username).execute()
    if not result.data:
        return jsonify({"success": False, "message": "Utilisateur non trouvé."})
    user = result.data[0]
    if user["password_hash"] == hash_password(password):
        return jsonify({
            "success": True,
            "message": "Connexion réussie",
            "user": {
                "username":  user["username"],
                "full_name": user["full_name"],
                "phone":     user["phone"]
            }
        })
    return jsonify({"success": False, "message": "Mot de passe incorrect."})

# ── RESERVATIONS ──────────────────────────────────────────────────────────────

@app.route('/api/reservations', methods=['GET'])
def get_reservations():
    username = request.args.get('username')
    user_id  = get_user_id(username)
    if not user_id:
        return jsonify([])
    result = supabase.table("reservations").select("*") \
                     .eq("user_id", user_id).neq("etat", "annule").execute()
    return jsonify([format_res(r) for r in result.data])


@app.route('/api/check-dispo', methods=['POST'])
def check_dispo():
    data         = request.json
    start        = data.get('start')
    end          = data.get('end')
    type_chambre = data.get('type')
    try:
        if type_chambre not in TYPES_CHAMBRES:
            return jsonify({"success": False, "message": "Type de chambre invalide"})
        start_obj = datetime.strptime(start, "%Y-%m-%d")
        end_obj   = datetime.strptime(end,   "%Y-%m-%d")
        if start_obj >= end_obj:
            return jsonify({"success": False, "message": "La date d'arrivée doit être avant la date de départ."})
        libres = chambres_libres(start, end)
        if not libres[type_chambre]:
            return jsonify({"success": False, "message": "Aucune chambre disponible"})
        nights = (end_obj - start_obj).days
        return jsonify({
            "success":     True,
            "price":       nights * TARIFS[type_chambre],
            "room_number": libres[type_chambre][0],
            "start":       start,
            "end":         end,
            "type":        type_chambre,
            "nights":      nights,
            "days":        nights + 1,
            "checkin":     "14:00",
            "checkout":    "12:00"
        })
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/reserve', methods=['POST'])
def reserve():
    data = request.json
    try:
        type_chambre = data['type_chambre']
        start        = data['start']
        end          = data['end']
        username     = data.get('username')
        # Récupérer l'id de l'utilisateur connecté
        user_id = get_user_id(username)
        if not user_id:
            return jsonify({"success": False, "message": "Utilisateur non trouvé."})
        if type_chambre not in TYPES_CHAMBRES:
            return jsonify({"success": False, "message": "Type de chambre invalide"})
        libres = chambres_libres(start, end)
        if not libres[type_chambre]:
            return jsonify({"success": False, "message": "Plus de chambres disponibles"})
        result = supabase.table("reservations").insert({
            "nom":          data['nom'],
            "prenom":       data['prenom'],
            "type_chambre": type_chambre,
            "datestart":    start,
            "dateend":      end,
            "contact":      data['contact'],
            "etat":         "valide",
            "num_chambre":  libres[type_chambre][0],
            "pin_code":     generate_pin(),
            "user_id":      user_id
        }).execute()
        return jsonify({"success": True, "reservation": format_res(result.data[0])})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/cancel-reservation', methods=['POST'])
def cancel_reservation():
    data   = request.json
    res_id = data.get('id')
    result = supabase.table("reservations").update({"etat": "annule"}).eq("id", res_id).execute()
    if result.data:
        return jsonify({"success": True,  "message": "Réservation annulée"})
    return jsonify({"success": False, "message": "Réservation non trouvée"})


@app.route('/api/modify-reservation', methods=['POST'])
def modify_reservation():
    try:
        data      = request.json
        res_id    = data.get('id')
        new_start = data.get('start')
        new_end   = data.get('end')
        if isinstance(res_id, str) and res_id.isdigit():
            res_id = int(res_id)
        result = supabase.table("reservations").select("*").eq("id", res_id).execute()
        if not result.data:
            return jsonify({"success": False, "message": "Réservation non trouvée"})
        res          = result.data[0]
        type_chambre = res["type_chambre"]
        start_obj    = datetime.strptime(new_start, "%Y-%m-%d")
        end_obj      = datetime.strptime(new_end,   "%Y-%m-%d")
        if start_obj >= end_obj:
            return jsonify({"success": False, "message": "La date d'arrivée doit être avant la date de départ."})
        libres = chambres_libres(new_start, new_end, exclude_id=res_id)
        if not libres[type_chambre]:
            return jsonify({"success": False, "message": "Dates non disponibles pour ce type de chambre"})
        supabase.table("reservations").update({
            "datestart": new_start,
            "dateend":   new_end,
            "etat":      "modifie"
        }).eq("id", res_id).execute()
        return jsonify({"success": True, "message": "Réservation modifiée avec succès"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


if __name__ == "__main__":
    app.run(debug=True)
