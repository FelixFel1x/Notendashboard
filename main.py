from flask import Flask, render_template, request, flash, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy

# --- Initialisierung der App und Konfiguration ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)  # Generiert einen zufälligen Secret Key. Wichtig für Sessions.
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///notenverwaltung.db'  # Definiert den Pfad zur SQLite-Datenbank.
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Deaktiviert das Tracking von Objektänderungen in SQLAlchemy.

# --- Initialisierung von Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Definiert die Route für den Login-View.

# --- Initialisierung von SQLAlchemy ---
db = SQLAlchemy(app)

# --- Benutzerdefinierte Jinja-Filter ---

# Filter, um Aufzählungen in Jinja-Templates zu ermöglichen.
app.jinja_env.filters['enumerate'] = enumerate

# Filter, um Zeitstempel in Jinja-Templates zu formatieren.
app.jinja_env.filters['strftime'] = lambda dt, fmt: dt.strftime(fmt) if dt else ''

# Filter, um ein Datum in einem bestimmten Format auszugeben.
@app.template_filter('date_format')
def date_format(value, format='%d.%m.%Y'):
    """Formatiert ein Datum in das gewünschte Format.

    Args:
        value: Das zu formatierende Datum (String oder datetime-Objekt).
        format: Das gewünschte Format (String).

    Returns:
        Das formatierte Datum als String oder den ursprünglichen Wert, falls ein Fehler auftritt.
    """
    if value is None:
        return ""
    try:
        if isinstance(value, str):
            value = datetime.strptime(value, '%Y-%m-%d')  # Konvertiert String zu datetime-Objekt.
        return value.strftime(format)
    except ValueError:
        return value

# --- Datenbank-Modelle ---

class User(UserMixin, db.Model):
    """
    Datenbankmodell für Benutzer.

    Attributes:
        id (int): Der eindeutige Identifikator des Benutzers (Primärschlüssel).
        username (str): Der Benutzername.
        password_hash (str): Der gehashte Passwort-String.
    """
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

    def check_password(self, password):
        """Überprüft, ob das angegebene Passwort mit dem gehashten Passwort des Benutzers übereinstimmt.

        Args:
            password (str): Das zu überprüfende Passwort.

        Returns:
            bool: True, wenn das Passwort übereinstimmt, sonst False.
        """
        return check_password_hash(self.password_hash, password)

class Major(db.Model):
    """
    Datenbankmodell für Studiengänge.

    Attributes:
        id (int): Der eindeutige Identifikator des Studiengangs (Primärschlüssel).
        name (str): Der Name des Studiengangs.
        user_id (int): Die ID des Benutzers, dem der Studiengang zugeordnet ist (Fremdschlüssel).
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('majors', lazy=True))  # Verknüpfung zum User

class Semester(db.Model):
    """
    Datenbankmodell für Semester.

    Attributes:
        id (int): Der eindeutige Identifikator des Semesters (Primärschlüssel).
        name (str): Der Name des Semesters (z.B. "WS2023", "SoSe2024").
        date (Date): Das Datum des Semesters (z.B. Startdatum).
        target_date (str): Das angestrebte Zieldatum für den Abschluss des Semesters.
        target_grade (float): Die angestrebte Zielnote für das Semester.
        major_id (int): Die ID des Studiengangs, zu dem das Semester gehört (Fremdschlüssel).
        user_id (int): Die ID des Benutzers, dem das Semester zugeordnet ist (Fremdschlüssel).
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date)
    target_date = db.Column(db.String(20))
    target_grade = db.Column(db.Float)
    major_id = db.Column(db.Integer, db.ForeignKey('major.id'), nullable=False)
    major = db.relationship('Major', backref=db.backref('semesters', lazy=True))  # Verknüpfung zum Major
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('semesters', lazy=True))  # Verknüpfung zum User
    modules = db.relationship('Module', backref='semester', lazy=True)  # Verknüpfung zu den Modulen

class Module(db.Model):
    """
    Datenbankmodell für Module.

    Attributes:
        id (int): Der eindeutige Identifikator des Moduls (Primärschlüssel).
        name (str): Der Name des Moduls.
        ects (int): Die ECTS-Punkte des Moduls.
        grade (float): Die Note des Moduls.
        date (Date): Das Datum, an dem das Modul abgeschlossen wurde.
        semester_id (int): Die ID des Semesters, zu dem das Modul gehört (Fremdschlüssel).
        user_id (int): Die ID des Benutzers, dem das Modul zugeordnet ist (Fremdschlüssel).
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    ects = db.Column(db.Integer)
    grade = db.Column(db.Float)
    date = db.Column(db.Date)
    semester_id = db.Column(db.Integer, db.ForeignKey('semester.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('modules', lazy=True))  # Verknüpfung zum User

# --- Datenbank-Initialisierung ---
with app.app_context():
    db.create_all()  # Erstellt die Datenbanktabellen, falls sie noch nicht existieren.

# --- Benutzer-Login-Funktionen ---

@login_manager.user_loader
def load_user(user_id):
    """Lädt einen Benutzer anhand seiner ID.

    Args:
        user_id (str): Die ID des Benutzers.

    Returns:
        User: Das Benutzerobjekt oder None, wenn kein Benutzer mit der angegebenen ID gefunden wurde.
    """
    return User.query.get(int(user_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Route für die Benutzerregistrierung.
    """
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash("Passwörter stimmen nicht überein.", "danger")
            return render_template('register.html')

        # Überprüft, ob der Benutzername bereits existiert.
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("Benutzername bereits vergeben.", "danger")
            return render_template('register.html')

        # Erstellt einen neuen Benutzer und speichert ihn in der Datenbank.
        hashed_password = generate_password_hash(password)  # Das Passwort wird gehasht.
        new_user = User(username=username, password_hash=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash("Registrierung erfolgreich. Bitte loggen Sie sich ein.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/', methods=['GET', 'POST'])
def login():
    """
    Route für den Benutzer-Login.
    """
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))  # Leitet eingeloggte Benutzer zum Dashboard weiter.

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        # Überprüft die Anmeldedaten und loggt den Benutzer ein.
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Falscher Benutzername oder Passwort', 'danger')

    return render_template('login.html')

# --- Dashboard-Funktionen ---

def calculate_weighted_average(modules):
    """Berechnet den gewichteten Notendurchschnitt für eine Liste von Modulen.

    Args:
        modules (list): Eine Liste von Modul-Objekten.

    Returns:
        float: Der gewichtete Notendurchschnitt oder None, wenn keine Module mit Noten vorhanden sind.
    """
    weighted_sum = 0
    total_ects = 0
    for module in modules:
        if module.grade is not None:
            weighted_sum += module.grade * module.ects
            total_ects += module.ects
    if total_ects > 0:
        return weighted_sum / total_ects
    else:
        return None

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    """
    Route für das Dashboard des Benutzers.
    """
    # Bearbeitungsmodus aus der Session laden (Standard: False)
    edit_mode = session.get('edit_mode', False)

    # Daten des aktuellen Benutzers aus der Datenbank laden
    major = Major.query.filter_by(user_id=current_user.id).first()
    semesters = Semester.query.filter_by(user_id=current_user.id).all()

    # Initialisiere semesters mit einem Beispiel, falls keine vorhanden.
    if not semesters:
        default_major = Major.query.filter_by(user_id=current_user.id).first()
        if not default_major:
            default_major = Major(name="Dein Studiengang", user_id=current_user.id)
            db.session.add(default_major)
            db.session.commit()

        # Beispieldaten
        semester1 = {
            "name": "Semester 1",
            "date": datetime(2023, 10, 1),
            "modules": [
                {"name": "Mathematik 1", "ects": 6, "grade": 1.7, "date": datetime(2023, 10, 26)},
                {"name": "Informatik 1", "ects": 6, "grade": 2.3, "date": datetime(2023, 11, 15)},
            ],
            "target_date": (datetime.now() + timedelta(days=3*365)).strftime('%Y-%m-%d'),
            "target_grade": 2.0,
            "major_id": default_major.id
        }
        semesters.append(semester1)

        # Konvertiert die Beispieldaten in Datenbankobjekte
        semester1_db = Semester(
            name=semester1["name"],
            date=semester1["date"],
            target_date=semester1["target_date"],
            target_grade=semester1["target_grade"],
            major_id=default_major.id,
            user_id=current_user.id
        )
        db.session.add(semester1_db)
        db.session.commit()

        for module_data in semester1["modules"]:
            module_db = Module(
                name=module_data["name"],
                ects=module_data["ects"],
                grade=module_data["grade"],
                date=module_data["date"],
                semester_id=semester1_db.id,
                user_id=current_user.id
            )
            db.session.add(module_db)
        db.session.commit()

        # Aktualisiere die semesters-Variable, um die Datenbankobjekte zu verwenden
        semesters = Semester.query.filter_by(user_id=current_user.id).all()

    # Ziele aus der Session laden (Standardwerte, falls nicht gesetzt)
    overall_target_date_str = session.get('overall_target_date', (datetime.now() + timedelta(days=3 * 365)).strftime('%Y-%m-%d'))
    overall_target_grade = session.get('overall_target_grade', 2.0)

    if request.method == 'POST':
        # Verarbeitet POST-Requests, die im Bearbeitungsmodus gesendet werden.
        if edit_mode:
            # Logik zum Speichern von Änderungen an Studiengang, Semestern und Modulen.
            if 'update_major' in request.form:
                major_name = request.form.get('major')
                major = Major.query.filter_by(user_id=current_user.id).first()
                if major:
                    major.name = major_name
                else:
                    major = Major(name=major_name, user_id=current_user.id)
                    db.session.add(major)
                db.session.commit()
            
            semester_index = -1
            if 'semester_index' in request.form:
                try:
                    semester_index = int(request.form.get('semester_index'))
                    # Überprüft, ob der Semesterindex gültig ist.
                    if semester_index < 0 or semester_index >= len(semesters):
                        raise ValueError("Ungültiger Semesterindex")
                    semester = semesters[semester_index]
                except ValueError:
                    flash("Ungültiger Semesterindex.", "danger")
                    return redirect(url_for('dashboard'))
                
            # --- Semester hinzufügen ---
            if 'add_semester' in request.form:
                semester_name = request.form.get('semester_name')
                semester_date_str = request.form.get('semester_date')
                # Konvertiert das Datum von String zu Date Objekt
                semester_date = datetime.strptime(semester_date_str, '%Y-%m-%d') if semester_date_str else None
                # Setzt das Zieldatum auf 6 Monate in der Zukunft, könnte aber beliebig geändert werden
                target_date_str = (datetime.now() + timedelta(days=180)).strftime('%Y-%m-%d')

                if semester_name:
                    major = Major.query.filter_by(user_id=current_user.id).first()
                    new_semester = Semester(name=semester_name, date=semester_date, target_date=target_date_str, target_grade=2.5, major_id=major.id, user_id=current_user.id)
                    db.session.add(new_semester)
                    db.session.commit()
                    semesters = Semester.query.filter_by(user_id=current_user.id).all()

            # --- Modul hinzufügen ---
            elif 'add_module' in request.form:
                try:
                    module_name = request.form.get('module_name')
                    ects = int(request.form.get('ects'))
                    date_str = request.form.get('date')
                    # Konvertiert das Datum von String zu Date Objekt
                    date = datetime.strptime(date_str, '%Y-%m-%d') if date_str else None
                    semester = semesters[semester_index]
                    if module_name and ects > 0:
                        new_module = Module(name=module_name, ects=ects, grade=None, date=date, semester_id=semester.id, user_id=current_user.id)
                        db.session.add(new_module)
                        db.session.commit() semesters = Semester.query.filter_by(user_id=current_user.id).all()
                    else:
                        flash("Bitte geben Sie einen Modulnamen und ECTS größer 0 ein.", "danger")
                except (ValueError, IndexError):
                    flash("Ungültige Eingabe für Semesterindex oder ECTS", "danger")

            # --- Modul aktualisieren ---
            elif 'update_module' in request.form:
                try:
                    module_index = int(request.form.get('module_index'))
                    module_name = request.form.get('module_name')
                    ects = int(request.form.get('ects'))
                    grade = request.form.get('grade')
                    date_str = request.form.get('date')
                    # Konvertiert das Datum von String zu Date Objekt
                    date = datetime.strptime(date_str, '%Y-%m-%d') if date_str else None

                    # Note in float umwandeln oder auf None setzen
                    if grade:
                        grade = float(grade)
                    else:
                        grade = None

                    module = semesters[semester_index].modules[module_index]

                    if module_name and ects > 0:
                        module.name = module_name
                        module.ects = ects
                        module.grade = grade
                        module.date = date
                        db.session.commit()
                        semesters = Semester.query.filter_by(user_id=current_user.id).all()
                    else:
                        flash("Bitte geben Sie einen Modulnamen und ECTS größer 0 ein.", "danger")

                except (ValueError, IndexError) as e:
                    flash(f"Fehler beim Aktualisieren des Moduls: {e}", "danger")

            # --- Modul entfernen ---
            elif 'remove_module' in request.form:
                try:
                    module_index = int(request.form.get('module_index'))
                    module = semesters[semester_index].modules[module_index]

                    db.session.delete(module)
                    db.session.commit()
                    semesters = Semester.query.filter_by(user_id=current_user.id).all()
                except (ValueError, IndexError):
                    flash("Ungültige Eingabe für Semester- oder Modulindex", "danger")

            # --- Semester entfernen ---
            elif 'remove_semester' in request.form:
                try:
                    semester = semesters[semester_index]
                    for module in semester.modules:
                        db.session.delete(module)
                    db.session.delete(semester)
                    db.session.commit()
                    semesters = Semester.query.filter_by(user_id=current_user.id).all()
                except (ValueError, IndexError):
                    flash("Ungültige Eingabe für Semesterindex", "danger")

            # --- Semester aktualisieren ---
            elif 'update_semester' in request.form:
                try:
                    semester_name = request.form.get('semester_name')
                    semester_date_str = request.form.get('semester_date')
                    # Konvertiert das Datum von String zu Date Objekt
                    semester_date = datetime.strptime(semester_date_str, '%Y-%m-%d') if semester_date_str else None
                    semester = semesters[semester_index]
                    if semester_name:
                        semester.name = semester_name
                        semester.date = semester_date
                        db.session.commit()
                        semesters = Semester.query.filter_by(user_id=current_user.id).all()
                    else:
                        flash("Bitte geben Sie einen Semester Name ein", "danger")

                except (ValueError, IndexError) as e:
                    flash(f"Fehler beim Aktualisieren des Semesters: {e}", "danger")

            # --- Semesterziele aktualisieren ---
            elif 'update_semester_targets' in request.form:
                try:
                    target_date_str = request.form.get('target_date')
                    target_grade = float(request.form.get('target_grade'))

                    semesters[semester_index].target_date = target_date_str
                    semesters[semester_index].target_grade = target_grade
                    db.session.commit()
                    semesters = Semester.query.filter_by(user_id=current_user.id).all()
                except (ValueError, IndexError) as e:
                    flash(f"Fehler beim Aktualisieren der Semesterziele: {e}", "danger")

            # --- Übergeordnete Ziele aktualisieren ---
            elif 'update_overall_targets' in request.form:
                overall_target_date_str = request.form.get('overall_target_date')
                try:
                    overall_target_grade = float(request.form.get('overall_target_grade'))
                except ValueError:
                    flash("Ungültige Eingabe für Gesamtzielnote", "danger")
                    overall_target_grade = session.get('overall_target_grade', 2.0)

                session['overall_target_date'] = overall_target_date_str
                session['overall_target_grade'] = overall_target_grade

    # --- Durchschnitt für jedes Semester berechnen ---
    for semester in semesters:
        semester.average = calculate_weighted_average(semester.modules)

    # --- Gesamtdurchschnitt berechnen ---
    all_modules = [module for semester in semesters for module in semester.modules]
    total_average = calculate_weighted_average(all_modules)

    # --- Berechnung des Fortschritts und der Farben für jedes Semester ---
    for semester in semesters:
        semester.ziel_nachricht = ""
        semester.ziel_klasse = ""

        if semester.average is not None:
            # Notenfortschritt
            if semester.average <= semester.target_grade:
                semester.ziel_nachricht = "Du bist auf einem guten Weg, dein Ziel zu erreichen!"
                semester.ziel_klasse = "ziel-erreicht"
            else:
                semester.ziel_nachricht = "Du musst dich noch etwas anstrengen, um deine Zielnote zu erreichen."
                semester.ziel_klasse = "ziel-gefaehrdet"

            # Zeitfortschritt
            try:
                target_date = datetime.strptime(semester.target_date, '%Y-%m-%d')
                vergangene_zeit = datetime.now() - (
                            target_date - timedelta(days=180))  # Annahme: Startdatum = Zieldatum - 6 Monate
                gesamte_zeit = timedelta(days=180)
                zeit_prozent = vergangene_zeit / gesamte_zeit * 100

                if zeit_prozent > 100:
                    semester.ziel_nachricht += " Achtung: Die Zeit für dieses Semester läuft ab!"
                    semester.ziel_klasse = "ziel-verfehlt"
            except ValueError:
                semester.ziel_nachricht += " Fehler beim Berechnen des Zeitfortschritts."
                semester.ziel_klasse = "ziel-verfehlt"
        else:
            semester.ziel_nachricht = "Es gibt noch keine Noten in diesem Semester."
            semester.ziel_klasse = "ziel-gefaehrdet"

        # Berechnung der Farbe für den Fortschrittsbalken im Semesterziel
        if semester.ziel_klasse == "ziel-erreicht":
            semester.fortschritt_farbe = "#4CAF50"  # Grün
        elif semester.ziel_klasse == "ziel-gefaehrdet":
            semester.fortschritt_farbe = "#ff9800"  # Orange
        else:
            semester.fortschritt_farbe = "#f44336"  # Rot

    # --- Berechnung des Fortschritts für das Gesamtziel ---
    overall_ziel_nachricht = ""
    overall_ziel_klasse = ""
    overall_fortschritt_prozent = 0

    if total_average is not None:
        if total_average <= overall_target_grade:
            overall_ziel_nachricht = "Du bist auf einem guten Weg, dein Gesamtziel zu erreichen!"
            overall_ziel_klasse = "ziel-erreicht"
            overall_fortschritt_prozent = 100
        else:
            overall_ziel_nachricht = "Du musst dich noch etwas anstrengen, um deine Gesamtzielnote zu erreichen."
            overall_ziel_klasse = "ziel-gefaehrdet"
            overall_fortschritt_prozent = int(
                overall_target_grade / total_average * 100) if total_average > 0 else 0

        try:
            overall_target_date = datetime.strptime(overall_target_date_str, '%Y-%m-%d')
            vergangene_zeit = datetime.now() - (
                        overall_target_date - timedelta(days=3 * 365))  # Annahme: Startdatum vor 3 Jahren
            gesamte_zeit = timedelta(days=3 * 365)
            zeit_prozent = vergangene_zeit / gesamte_zeit * 100

            if zeit_prozent > 100:
                overall_ziel_nachricht += " Achtung: Die Zeit für dein Studium läuft ab!"
                overall_ziel_klasse = "ziel-verfehlt"
        except ValueError:
            overall_ziel_nachricht += " Fehler beim Berechnen des Zeitfortschritts."
            overall_ziel_klasse = "ziel-verfehlt"

    else:
        overall_ziel_nachricht = "Es gibt noch keine Noten, um den Fortschritt zu berechnen."
        overall_ziel_klasse = "ziel-gefaehrdet"

    # Berechnung der Farbe für den Fortschrittsbalken im Gesamtziel
    if overall_ziel_klasse == "ziel-erreicht":
        overall_fortschritt_farbe = "#4CAF50"  # Grün
    elif overall_ziel_klasse == "ziel-gefaehrdet":
        overall_fortschritt_farbe = "#ff9800"  # Orange
    else:
        overall_fortschritt_farbe = "#f44336"  # Rot

    # --- Überprüfen, ob ein Semester abgeschlossen wurde, und ggf. Flash-Nachricht anzeigen ---
    for semester in semesters:
        if semester.average is not None:
            try:
                semester_ziel_datum = datetime.strptime(semester.target_date, '%Y-%m-%d')
            except ValueError:
                flash(
                    f"Ungültiges Zieldatum Format für Semester {semester.name}. Bitte verwenden Sie das Format JJJJ-MM-TT.",
                    "danger")
                continue  # Zum nächsten Semester springen, falls das Format ungültig ist

            toleranz_tage = 30
            if semester_ziel_datum is not None and datetime.now() > semester_ziel_datum + timedelta(
                    days=toleranz_tage):
                if not session.get(f'semester_{semester.id}_abgeschlossen'):
                    flash(f"Das Semester '{semester.name}' ist abgeschlossen! Durchschnittsnote: {semester.average:.2f}",
                          "success")
                    session[f'semester_{semester.id}_abgeschlossen'] = True
            elif all(module.grade is not None for module in semester.modules):
                if not session.get(f'semester_{semester.id}_abgeschlossen'):
                    flash(f"Das Semester '{semester.name}' ist abgeschlossen! Durchschnittsnote: {semester.average:.2f}",
                          "success")
                    session[f'semester_{semester.id}_abgeschlossen'] = True
            else:
                # Zurücksetzen des Flags, falls das Semester noch nicht abgeschlossen ist
                session[f'semester_{semester.id}_abgeschlossen'] = False

    return render_template('dashboard.html', semesters=semesters, total_average=total_average,
                           edit_mode=edit_mode, major=major, current_user=current_user,
                           overall_target_date_str=overall_target_date_str,
                           overall_target_grade=overall_target_grade,
                           overall_ziel_nachricht=overall_ziel_nachricht, overall_ziel_klasse=overall_ziel_klasse,
                           overall_fortschritt_prozent=overall_fortschritt_prozent,
                           overall_fortschritt_farbe=overall_fortschritt_farbe)

@app.route('/toggle_edit_mode')
@login_required
def toggle_edit_mode():
    """
    Route zum Umschalten des Bearbeitungsmodus.
    """
    session['edit_mode'] = not session.get('edit_mode', False)
    return redirect(url_for('dashboard'))

@app.route('/logout')
@login_required
def logout():
    """
    Route zum Ausloggen des Benutzers.
    """
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)