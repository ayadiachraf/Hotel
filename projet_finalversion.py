import json
import re
import os
import random
from datetime import datetime

import hashlib
from flask import Flask, request, jsonify
from flask_cors import CORS
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

class User:
    def __init__(self, username, password_hash, full_name, email, phone=""):
        self.username = username
        self.password_hash = password_hash
        self.full_name = full_name
        self.email = email
        self.phone = phone

    def to_dict(self):
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone
        }

    @staticmethod
    def from_dict(d):
        return User(d["username"], d["password_hash"], d["full_name"], d["email"], d.get("phone", ""))


class AuthManager:
    def __init__(self, fichier_users="users.json"):
        self.fichier_users = fichier_users
        self.users = {}
        self.load()

    def load(self):
        if os.path.exists(self.fichier_users):
            try:
                with open(self.fichier_users, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for d in data:
                        user = User.from_dict(d)
                        self.users[user.username] = user
            except Exception as e:
                print(f"Erreur chargement utilisateurs: {e}")

    def save(self):
        try:
            data = [u.to_dict() for u in self.users.values()]
            with open(self.fichier_users, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Erreur sauvegarde utilisateurs: {e}")

    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

    def register(self, username, password, full_name, email, phone=""):
        if not username or not password:
            return False, "Nom d'utilisateur et mot de passe requis."
        if username in self.users:
            return False, "Cet utilisateur existe déjà."
        
        password_hash = self.hash_password(password)
        new_user = User(username, password_hash, full_name, email, phone)
        self.users[username] = new_user
        self.save()
        return True, "Inscription réussie."

    def login(self, username, password):
        if username not in self.users:
            return False, "Utilisateur non trouvé."
        
        password_hash = self.hash_password(password)
        if self.users[username].password_hash == password_hash:
            return True, self.users[username]
        return False, "Mot de passe incorrect."


class Reservation:
    auto_id = 1
    TYPES_CHAMBRES = ["simple", "double", "suite"]
    
    def __init__(self, nom="", prenom="", type_chambre="", datestart="", dateend="", contact="", pin_code=None, skip_validation=False, is_temp=False):
        self.id = None
        self.nom = nom
        self.prenom = prenom
        self.type_chambre = type_chambre
        self.datestart = datestart
        self.dateend = dateend
        self.contact = contact
        self.etat = "valide"
        self.num_chambre = None
        self.datestart_obj = None
        self.dateend_obj = None
        
        if pin_code is None and not skip_validation:
            self.pin_code = self.generate_pin()
        else:
            self.pin_code = pin_code
        
        if not skip_validation:
            self.validate_type_chambre(type_chambre)
            self.datestart_obj = self.validate_date(datestart)
            self.dateend_obj = self.validate_date(dateend)
            self.validate_range()
            self.validate_contact(contact)
            
        if not skip_validation and not is_temp:
            self.id = Reservation.auto_id
            Reservation.auto_id += 1
    
    def generate_pin(self):
        return str(random.randint(1000, 9999))
    
    def validate_type_chambre(self, type_chambre):
        if type_chambre not in Reservation.TYPES_CHAMBRES:
            raise ValueError(f"Type invalide. Choix possibles: {', '.join(Reservation.TYPES_CHAMBRES)}")
    
    def validate_contact(self, contact):
        if not contact:
            raise ValueError("Le contact ne peut pas etre vide")
        
        email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        phone_pattern = r'^[\d\s\+\-\(\)]{8,}$'
        
        if not (re.match(email_pattern, contact) or re.match(phone_pattern, contact)):
            raise ValueError("Contact invalide (email ou telephone d'au moins 8 chiffres requis)")
    
    def validate_date(self, date):
        if not date:
            raise ValueError("La date ne peut pas etre vide")
        try:
            return datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Date invalide : {date}. Format attendu: AAAA-MM-JJ")
    
    def validate_range(self):
        if self.datestart_obj >= self.dateend_obj:
            raise ValueError("La date d'arrivee doit etre avant la date de depart.")
        return True
    
    def from_dict(self, d):
        self.id = d["id"]
        self.nom = d["nom"]
        self.prenom = d["prenom"]
        self.type_chambre = d["type_chambre"]
        self.datestart = d["start"]
        self.dateend = d["end"]
        self.datestart_obj = datetime.strptime(self.datestart, "%Y-%m-%d")
        self.dateend_obj = datetime.strptime(self.dateend, "%Y-%m-%d")
        self.etat = d["etat"]
        self.num_chambre = d.get("num_chambre", None)
        self.contact = d.get("contact", "")
        self.pin_code = d.get("pin_code", None)
        self.username = d.get("username", None)
        return self
    
    def to_dict(self):
        return {
            "id": self.id,
            "nom": self.nom,
            "prenom": self.prenom,
            "type_chambre": self.type_chambre,
            "start": self.datestart,
            "end": self.dateend,
            "etat": self.etat,
            "num_chambre": self.num_chambre,
            "contact": self.contact,
            "pin_code": self.pin_code,
            "username": getattr(self, 'username', None)
        }
    
    def prix(self):
        tarifs = {"simple": 30, "double": 50, "suite": 70}
        nombre_jours = (self.dateend_obj - self.datestart_obj).days
        return nombre_jours * tarifs[self.type_chambre]
    
    def __str__(self):
        return (f"ID: {self.id} | {self.nom} {self.prenom} | "
                f"Chambre {self.type_chambre} (N{self.num_chambre}) | "
                f"Du {self.datestart} au {self.dateend} | "
                f"Prix: {self.prix()} euros | Contact: {self.contact} | Etat: {self.etat}")


def generer_facture(reservation, dossier="./"):
    if not isinstance(reservation, Reservation):
        raise ValueError("Doit fournir une instance Reservation.")

    nom_fichier = os.path.join(dossier, f"facture_{reservation.id}.pdf")
    c = canvas.Canvas(nom_fichier, pagesize=A4)
    width, height = A4

    x_margin = 50
    y = height - 50

    c.setFont("Helvetica-Bold", 16)
    c.drawString(x_margin, y, "FACTURE / RECU")
    y -= 30

    c.setFont("Helvetica", 10)
    c.drawString(x_margin, y, f"Date emission : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    y -= 20

    c.drawString(x_margin, y, f"ID reservation : {reservation.id}")
    y -= 15
    c.drawString(x_margin, y, f"Nom : {reservation.nom} {reservation.prenom}")
    y -= 15
    c.drawString(x_margin, y, f"Contact : {reservation.contact}")
    y -= 15
    c.drawString(x_margin, y, f"Type chambre : {reservation.type_chambre}")
    y -= 15
    c.drawString(x_margin, y, f"N chambre : {reservation.num_chambre}")
    y -= 15
    c.drawString(x_margin, y, f"Date d'arrivee : {reservation.datestart}")
    y -= 15
    c.drawString(x_margin, y, f"Date de depart : {reservation.dateend}")
    y -= 15
    
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x_margin, y, f"CODE PIN : {reservation.pin_code}")
    c.setFont("Helvetica", 10)
    y -= 20

    total = reservation.prix()
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_margin, y, f"Total a payer : {total} euros")
    y -= 30

    c.setFont("Helvetica", 9)
    c.drawString(x_margin, y, "Merci pour votre reservation.")
    y -= 12
    c.drawString(x_margin, y, "Conditions: paiement a l'arrivee. Pour annulation, contactez l'hotel.")
    y -= 24

    c.line(x_margin, y, x_margin + 200, y)
    y -= 12
    c.drawString(x_margin, y, "Signature etablissement")

    c.showPage()
    c.save()
    return nom_fichier


class Hotel:
    chambres = {
        "simple": [100 + i for i in range(1, 100)],
        "double": [200 + i for i in range(1, 100)],
        "suite": [300 + i for i in range(1, 100)]
    }
    
    def __init__(self, fichierJson):
        self.fichierJson = fichierJson
        self.reservations = []
        self.load()
    
    def load(self):
        try:
            with open(self.fichierJson, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.reservations = [Reservation(skip_validation=True).from_dict(d) for d in data]
            
            if self.reservations:
                max_id = max(r.id for r in self.reservations)
                Reservation.auto_id = max_id + 1
                print(f"{len(self.reservations)} reservations chargees. Prochain ID: {Reservation.auto_id}")
        except FileNotFoundError:
            self.reservations = []
            print("Aucun fichier de reservations trouve. Demarrage avec liste vide.")
        except json.JSONDecodeError as e:
            print(f"Erreur de lecture JSON: {e}")
            self.reservations = []
        except Exception as e:
            print(f"Erreur inattendue lors du chargement: {e}")
            self.reservations = []
    
    def save(self):
        try:
            data = [res.to_dict() for res in self.reservations]
            with open(self.fichierJson, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print("Reservations sauvegardees avec succes")
        except Exception as e:
            print(f"Erreur lors de la sauvegarde: {e}")
    
    def chambres_libres(self, start, end):
        start_obj = datetime.strptime(start, "%Y-%m-%d")
        end_obj = datetime.strptime(end, "%Y-%m-%d")
        libres = {}
        
        for type_chambre, nums in Hotel.chambres.items():
            libres[type_chambre] = []
            for num in nums:
                libre = True
                for r in self.reservations:
                    if r.num_chambre == num and r.type_chambre == type_chambre and r.etat != "annule":
                        r_start = datetime.strptime(r.datestart, "%Y-%m-%d")
                        r_end = datetime.strptime(r.dateend, "%Y-%m-%d")
                        if not (end_obj <= r_start or start_obj >= r_end):
                            libre = False
                            break
                if libre:
                    libres[type_chambre].append(num)
        return libres
    
    def add(self, res):
        if not isinstance(res, Reservation):
            print(f"{res} n'est pas une reservation valide")
            return False
        
        libres = self.chambres_libres(res.datestart, res.dateend)
        
        if not libres[res.type_chambre]:
            print(f"\nDesole {res.nom},")
            print(f"Aucune chambre de type '{res.type_chambre}' disponible pour ces dates\n")
            print("Chambres disponibles pour ces dates:")
            for t, nums in libres.items():
                if nums:
                    print(f"   {t.capitalize()}: {len(nums)} chambre(s)")
            return False
        
        res.num_chambre = libres[res.type_chambre][0]
        self.reservations.append(res)
        print(f"\nReservation confirmee!")
        print(f"   Client: {res.nom} {res.prenom}")
        print(f"   Chambre N{res.num_chambre} ({res.type_chambre})")
        print(f"   Periode: {res.datestart} -> {res.dateend}")
        print(f"   Prix total: {res.prix()} euros")
        print(f"   ID reservation: #{res.id}")
        print(f"\n   CODE PIN : {res.pin_code}")
        print(f"   IMPORTANT: Conservez ce code PIN pour modifier ou annuler votre reservation!")
        
        try:
            facture = generer_facture(res)
            print(f"\n   Facture generee: {facture}")
        except Exception as e:
            print(f"   Erreur generation facture: {e}")
        
        self.save()
        return True
    
    def find_by_id(self, id_res):
        for r in self.reservations:
            if r.id == id_res:
                return r
        return None
    
    def modify(self, res):
        if not isinstance(res, Reservation):
            print("Reservation non valide")
            return
        
        if res.id not in [r.id for r in self.reservations]:
            print("ID introuvable")
            return
        
        print("\nVerification du code PIN requise")
        pin_verification = input("Entrez le code PIN de la reservation: ").strip()
        
        if res.pin_code is None:
            print("Cette reservation n'a pas de code PIN (ancienne reservation).")
            print("   Veuillez contacter l'hotel pour la modifier.")
            return
        
        if pin_verification != res.pin_code:
            print("Code PIN incorrect! Acces refuse.")
            return
        
        print(f"\n=== Modification de la reservation #{res.id} ===")
        print("(Appuyez sur Entree pour garder la valeur actuelle)\n")
        
        try:
            new_nom = input(f"Nouveau nom ({res.nom}): ").strip() or res.nom
            new_prenom = input(f"Nouveau prenom ({res.prenom}): ").strip() or res.prenom
            
            while True:
                new_type = input(f"Nouveau type de chambre ({res.type_chambre}) [{'/'.join(Reservation.TYPES_CHAMBRES)}]: ").strip() or res.type_chambre
                if new_type in Reservation.TYPES_CHAMBRES:
                    break
                print(f"Type invalide. Choix: {', '.join(Reservation.TYPES_CHAMBRES)}")
            
            new_start = input(f"Nouvelle date d'arrivee ({res.datestart}): ").strip() or res.datestart
            new_end = input(f"Nouvelle date de depart ({res.dateend}): ").strip() or res.dateend
            new_contact = input(f"Nouveau contact ({res.contact}): ").strip() or res.contact
            
            temp_res = Reservation(new_nom, new_prenom, new_type, new_start, new_end, new_contact)
            
            ancien_num = res.num_chambre
            ancien_type = res.type_chambre
            res.num_chambre = None
            
            libres = self.chambres_libres(new_start, new_end)
            
            if new_type == ancien_type and ancien_num in libres[new_type]:
                temp_res.num_chambre = ancien_num
            elif libres[new_type]:
                temp_res.num_chambre = libres[new_type][0]
            else:
                res.num_chambre = ancien_num
                print(f"Aucune chambre de type '{new_type}' disponible pour ces dates")
                return
            
            res.nom = temp_res.nom
            res.prenom = temp_res.prenom
            res.type_chambre = temp_res.type_chambre
            res.datestart = temp_res.datestart
            res.dateend = temp_res.dateend
            res.datestart_obj = temp_res.datestart_obj
            res.dateend_obj = temp_res.dateend_obj
            res.contact = temp_res.contact
            res.num_chambre = temp_res.num_chambre
            res.etat = "modifie"
            
            self.save()
            print(f"Reservation #{res.id} modifiee avec succes")
            
            try:
                facture = generer_facture(res)
                print(f"Nouvelle facture generee: {facture}")
            except Exception as e:
                print(f"Erreur generation facture: {e}")
            
        except ValueError as e:
            res.num_chambre = ancien_num
            print(f"Erreur de validation: {e}")
    
    def annuler_reservation(self, res):
        if not isinstance(res, Reservation):
            print("Reservation non valide")
            return
        
        if res.id not in [r.id for r in self.reservations]:
            print("ID introuvable")
            return
        
        print("\nVerification du code PIN requise")
        pin_verification = input("Entrez le code PIN de la reservation: ").strip()
        
        if pin_verification != res.pin_code:
            print("Code PIN incorrect! Acces refuse.")
            return
        
        if res.etat == "annule":
            print("Cette reservation est deja annulee")
            return
        
        res.etat = "annule"
        self.save()
        print(f"Reservation #{res.id} annulee avec succes")
    
    def verifier_disponibilite(self):
        print("\n=== Verification de disponibilite ===")
        
        try:
            start = input("Date de debut (AAAA-MM-JJ): ").strip()
            end = input("Date de fin (AAAA-MM-JJ): ").strip()
            
            datetime.strptime(start, "%Y-%m-%d")
            datetime.strptime(end, "%Y-%m-%d")
            
            libres = self.chambres_libres(start, end)
            
            print(f"\nChambres disponibles du {start} au {end}:")
            total = 0
            for t, nums in libres.items():
                if nums:
                    print(f"   {t.capitalize()}: {len(nums)} chambre(s)")
                    total += len(nums)
            
            if total == 0:
                print("   Aucune chambre disponible pour ces dates")
            else:
                print(f"\n   Total: {total} chambre(s) disponible(s)")
                
        except ValueError as e:
            print(f"Erreur: {e}")
    
    def rechercher_par_nom(self, nom):
        resultats = [r for r in self.reservations 
                    if nom.lower() in r.nom.lower() and r.etat != "annule"]
        return resultats


def menu(hotel):
    while True:
        print("\n" + "="*60)
        print("       SYSTEME DE GESTION DE RESERVATIONS D'HOTEL")
        print("="*60)
        print("1. Verifier la disponibilite")
        print("2. Effectuer une reservation")
        print("3. Modifier une reservation")
        print("4. Annuler une reservation")
        print("5. Afficher toutes les reservations")
        print("6. Rechercher par nom")
        print("7. Generer/Regenerer une facture")
        print("8. Quitter")
        print("="*60)
        
        choix = input("Votre choix: ").strip()
        
        if choix == "1":
            hotel.verifier_disponibilite()
            
        elif choix == "2":
            print("\n=== NOUVELLE RESERVATION ===")
            print("-" * 40)
            try:
                nom = input("Nom: ").strip()
                prenom = input("Prenom: ").strip()
                print(f"Types disponibles: {', '.join(Reservation.TYPES_CHAMBRES)}")
                type_chambre = input("Type de chambre: ").strip().lower()
                datestart = input("Date d'arrivee (AAAA-MM-JJ): ").strip()
                dateend = input("Date de depart (AAAA-MM-JJ): ").strip()
                contact = input("Contact (email ou telephone): ").strip()
                
                res = Reservation(nom, prenom, type_chambre, datestart, dateend, contact)
                hotel.add(res)
            except ValueError as e:
                print(f"Erreur: {e}")
                
        elif choix == "3":
            try:
                id_modif = int(input("ID de la reservation a modifier: "))
                res = hotel.find_by_id(id_modif)
                if res:
                    if res.etat == "annule":
                        print("Impossible de modifier une reservation annulee")
                    else:
                        hotel.modify(res)
                else:
                    print("Reservation non trouvee")
            except ValueError:
                print("ID invalide")
                
        elif choix == "4":
            try:
                id_annul = int(input("ID de la reservation a annuler: "))
                res = hotel.find_by_id(id_annul)
                if res:
                    hotel.annuler_reservation(res)
                else:
                    print("Reservation non trouvee")
            except ValueError:
                print("ID invalide")
                
        elif choix == "5":
            reservations_afficher = [r for r in hotel.reservations if r.etat != "annule"]
            if not reservations_afficher:
                print("\nAucune reservation active")
            else:
                try:
                    reservations_afficher.sort(key=lambda r: r.datestart_obj)
                    print(f"\n{len(reservations_afficher)} reservation(s) active(s):")
                    print("-" * 120)
                    for r in reservations_afficher:
                        print(r)
                    print("-" * 120)
                except Exception as e:
                    print(f"Erreur lors de l'affichage: {e}")
                    
        elif choix == "6":
            nom_recherche = input("Nom a rechercher: ").strip()
            resultats = hotel.rechercher_par_nom(nom_recherche)
            if resultats:
                print(f"\n{len(resultats)} resultat(s) trouve(s):")
                print("-" * 120)
                for r in resultats:
                    print(r)
                print("-" * 120)
            else:
                print("Aucune reservation trouvee")
                
        elif choix == "7":
            try:
                id_res = int(input("ID de la reservation: "))
                res = hotel.find_by_id(id_res)
                if not res:
                    print("Reservation introuvable")
                else:
                    facture = generer_facture(res)
                    print(f"Facture generee: {facture}")
            except ValueError:
                print("ID invalide")
            except Exception as e:
                print(f"Erreur: {e}")
                
        elif choix == "8":
            print("\nAu revoir! Merci d'avoir utilise notre systeme de reservation.")
            break
            
        else:
            print("Choix invalide. Veuillez choisir entre 1 et 8.")



# --- INTEGRATION FLASK ---
app = Flask(__name__)
CORS(app)  # Autorise les requêtes depuis l'interface HTML

hotel = Hotel("reservations.json")
auth = AuthManager("users.json")

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    success, message = auth.register(
        data.get('username'),
        data.get('password'),
        data.get('full_name', ''),
        data.get('email', ''),
        data.get('phone', '')
    )
    return jsonify({"success": success, "message": message})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    success, result = auth.login(data.get('username'), data.get('password'))
    if success:
        return jsonify({
            "success": True,
            "message": "Connexion réussie",
            "user": {"username": result.username, "full_name": result.full_name, "phone": result.phone}
        })
    return jsonify({"success": False, "message": result})

@app.route('/reservations', methods=['GET'])
def get_reservations():
    username = request.args.get('username')
    user_res = [r.to_dict() for r in hotel.reservations if r.username == username and r.etat != "annule"]
    return jsonify(user_res)

@app.route('/check-dispo', methods=['POST'])
def check_dispo():
    data = request.json
    try:
        start = data.get('start')
        end = data.get('end')
        type_chambre = data.get('type')
        
        # Validation rapide (is_temp=True pour ne pas gâcher d'ID)
        temp_res = Reservation("Temp", "Temp", type_chambre, start, end, "temp@temp.com", is_temp=True)
        libres = hotel.chambres_libres(start, end)
        
        if not libres[type_chambre]:
            return jsonify({"success": False, "message": "Aucune chambre disponible"})
        
        nights = (temp_res.dateend_obj - temp_res.datestart_obj).days
        days = nights + 1
        
        return jsonify({
            "success": True,
            "price": temp_res.prix(),
            "room_number": libres[type_chambre][0],
            "start": start,
            "end": end,
            "type": type_chambre,
            "nights": nights,
            "days": days,
            "checkin": "14:00",
            "checkout": "12:00"
        })
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/reserve', methods=['POST'])
def reserve():
    data = request.json
    try:
        res = Reservation(
            data['nom'], data['prenom'], data['type_chambre'],
            data['start'], data['end'], data['contact']
        )
        res.username = data.get('username') # Lier à l'utilisateur connecté
        if hotel.add(res):
            return jsonify({"success": True, "reservation": res.to_dict()})
        return jsonify({"success": False, "message": "Plus de chambres disponibles"})
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/cancel-reservation', methods=['POST'])
def cancel_reservation():
    data = request.json
    res_id = data.get('id')
    for r in hotel.reservations:
        if r.id == res_id:
            r.etat = "annule"
            hotel.save()
            return jsonify({"success": True, "message": "Réservation annulée"})
    return jsonify({"success": False, "message": "Réservation non trouvée"})

@app.route('/modify-reservation', methods=['POST'])
def modify_reservation():
    try:
        data = request.json
        res_id = data.get('id')
        new_start = data.get('start')
        new_end = data.get('end')
        
        # S'assurer que res_id est un entier
        if isinstance(res_id, str) and res_id.isdigit():
            res_id = int(res_id)
        
        for r in hotel.reservations:
            if r.id == res_id:
                # Vérifier la disponibilité pour les nouvelles dates
                # On exclut temporairement cette réservation pour le test de disponibilité
                old_etat = r.etat
                r.etat = "annule" # Pour que chambres_libres l'ignore
                try:
                    libres = hotel.chambres_libres(new_start, new_end)
                except Exception as e:
                    r.etat = old_etat
                    return jsonify({"success": False, "message": f"Erreur de date : {e}"})
                r.etat = old_etat
                
                if not libres[r.type_chambre]:
                    return jsonify({"success": False, "message": "Dates non disponibles pour ce type de chambre"})
                
                # Mettre à jour les dates
                r.datestart = new_start
                r.dateend = new_end
                r.datestart_obj = datetime.strptime(new_start, "%Y-%m-%d")
                r.dateend_obj = datetime.strptime(new_end, "%Y-%m-%d")
                r.validate_range()
                hotel.save()
                return jsonify({"success": True, "message": "Réservation modifiée avec succès"})
                
        return jsonify({"success": False, "message": "Réservation non trouvée"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)})

if __name__ == "__main__":
    print("Serveur démarré sur http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
