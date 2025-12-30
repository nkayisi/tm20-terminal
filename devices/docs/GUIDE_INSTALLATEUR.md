# Guide Installateur Terrain - Terminal TM20-WIFI

## 📋 Checklist Pré-Installation

### Matériel requis

- [ ] Terminal TM20-WIFI
- [ ] Câble d'alimentation 12V DC
- [ ] Câble réseau RJ45 (si connexion filaire)
- [ ] Point d'accès WiFi (SSID + mot de passe)
- [ ] Adresse IP du serveur cloud
- [ ] Port serveur : **7788**

### Informations à collecter

- [ ] Numéro de série (SN) du terminal (étiquette arrière)
- [ ] Adresse IP du serveur : `_______________`
- [ ] SSID WiFi : `_______________`
- [ ] Mot de passe WiFi : `_______________`

---

## 🔌 Étape 1 : Branchement Physique

### Connexion électrique

1. Brancher le câble d'alimentation 12V DC
2. Vérifier que le voyant s'allume
3. Attendre le démarrage complet (~30 secondes)

### Connexion réseau (optionnel si WiFi)

1. Brancher le câble RJ45 au port réseau
2. Vérifier le voyant réseau (clignotant = actif)

---

## ⚙️ Étape 2 : Configuration Réseau

### Accès au menu administrateur

1. Appuyer sur **M/OK** pendant 3 secondes
2. Entrer le code admin : `0000` (par défaut)
3. Naviguer avec ▲/▼, valider avec M/OK

### Configuration WiFi

1. Menu → **Comm.** → **WiFi**
2. Activer WiFi : **ON**
3. Recherche réseau → Sélectionner le SSID
4. Entrer le mot de passe WiFi
5. Valider et attendre la connexion

### Vérification IP

1. Menu → **Comm.** → **Ethernet**
2. Noter l'adresse IP attribuée : `_______________`
3. Vérifier que le masque et la passerelle sont corrects

---

## 🌐 Étape 3 : Configuration Cloud (Serveur)

### Paramètres Cloud

1. Menu → **Comm.** → **Cloud Setting**
2. Configurer :

| Paramètre   | Valeur         |
| ----------- | -------------- |
| Mode        | **Enabled**    |
| Protocol    | **WebSocket**  |
| Server IP   | `[IP_SERVEUR]` |
| Server Port | `7788`         |
| Path        | `/ws/tm20/`    |

### Exemple complet

```
Server: ws://192.168.1.100:7788/ws/tm20/
```

### Validation

1. Appuyer sur **M/OK** pour sauvegarder
2. Le terminal affiche "Connecting..."
3. Après quelques secondes : "Cloud Connected ✓"

---

## ✅ Étape 4 : Vérification de la Connexion

### Sur le terminal

- Icône cloud visible dans la barre de statut
- Pas de message d'erreur

### Sur le serveur (Dashboard)

1. Ouvrir : `http://[IP_SERVEUR]:8000/dashboard/`
2. Vérifier que le terminal apparaît avec statut **Online**
3. Le SN doit correspondre à celui de l'étiquette

### Test de pointage

1. Enregistrer une empreinte test (Menu → User → Add)
2. Effectuer un pointage
3. Vérifier sur le dashboard que le log apparaît

---

## 🕐 Étape 5 : Synchronisation Horaire

### Vérification automatique

- L'heure se synchronise automatiquement à la connexion
- Vérifier que l'heure affichée est correcte

### Synchronisation manuelle (si nécessaire)

1. Sur le dashboard : cliquer sur l'icône horloge du terminal
2. Ou : Menu → System → Date/Time

---

## 🔧 Paramètres Avancés (Optionnel)

### Paramètres de porte

1. Menu → **Access** → **Door Setting**
   - Delay : 5 secondes (durée ouverture)
   - Sensor : selon câblage

### Paramètres de pointage

1. Menu → **Attendance** → **Setting**
   - Mode : In/Out ou Auto
   - Voice : On/Off

---

## ❌ Problèmes Courants

### "Network Error" ou "No IP"

| Cause           | Solution                    |
| --------------- | --------------------------- |
| Câble débranché | Vérifier connexion RJ45     |
| WiFi incorrect  | Vérifier SSID/mot de passe  |
| DHCP désactivé  | Activer DHCP sur le routeur |

### "Cloud Disconnected"

| Cause               | Solution                      |
| ------------------- | ----------------------------- |
| Mauvaise IP serveur | Vérifier l'adresse IP         |
| Port bloqué         | Vérifier firewall (port 7788) |
| Serveur down        | Vérifier état du serveur      |
| Path incorrect      | Doit être `/ws/tm20/`         |

### "Connection Timeout"

| Cause             | Solution              |
| ----------------- | --------------------- |
| Réseau instable   | Vérifier signal WiFi  |
| Serveur surchargé | Vérifier logs serveur |

### Terminal non visible sur dashboard

1. Vérifier que le SN correspond
2. Redémarrer le terminal
3. Vérifier les logs serveur : `docker compose logs django-ws`

---

## 📞 Support Technique

### Informations à fournir

- Numéro de série (SN) : `_______________`
- Version firmware : `_______________`
- Adresse IP terminal : `_______________`
- Message d'erreur exact : `_______________`

### Récupérer le firmware

Menu → System → Info → Firmware Version

### Logs serveur

```bash
docker compose logs -f django-ws
```

---

## ✔️ Checklist Validation Installation

### Configuration réseau

- [ ] Terminal connecté au réseau (WiFi ou câble)
- [ ] Adresse IP attribuée
- [ ] Ping serveur OK depuis le réseau local

### Configuration cloud

- [ ] Paramètres cloud configurés
- [ ] Icône cloud visible
- [ ] Statut "Online" sur dashboard

### Test fonctionnel

- [ ] Heure synchronisée
- [ ] Test pointage OK
- [ ] Log visible sur dashboard

### Documentation

- [ ] SN noté dans le dossier client
- [ ] Photo de l'installation
- [ ] Formulaire de mise en service signé

---

## 📝 Notes d'Installation

```
Date : _______________
Technicien : _______________
Site : _______________
SN Terminal : _______________
IP Terminal : _______________
Observations : _______________________________________________
____________________________________________________________
Signature client : _______________
```
