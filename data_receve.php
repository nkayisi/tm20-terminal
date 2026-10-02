<?php
// Lire le corps brut de la requête
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);
require 'base.php';
header("Access-Control-Allow-Origin: *");
header("Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS");
header("Access-Control-Allow-Headers: Content-Type, Authorization");

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit();
}
$rawJson = file_get_contents('php://input');
$response = [];
header('Content-Type: application/json');
// Décoder en tableau associatif

function ecartHeure($heurePasse,$heureActuelle)
{
    // Heure actuelle sans secondes
  //  $heureActuelle = date("H:i");

    // Convertir en timestamp
    $t1 = strtotime($heureActuelle);
    $t2 = strtotime($heurePasse);

    // Différence en secondes
    $diff = $t1 - $t2;

    // Gestion du signe
    $signe = '';
    if ($diff < 0) {
        $signe = '-';
        $diff = abs($diff);
    }

    // Conversion en minutes
    $minutes = floor($diff / 60);

    // Si >= 60 min → heures + minutes
    if ($minutes >= 60) {
        $heures = floor($minutes / 60);
        $resteMin = $minutes % 60;

        if ($resteMin == 0) {
			if($signe=="-"){
				return [
					"retard"=>"non",
					"interval"=>$signe . $heures . " h"
				];
			}else{
				return [
					"retard"=>"oui",
					"interval"=>$signe . $heures . " h"
				];
			}
             
        } else {
			if($signe=="-"){
				return [
					"retard"=>"non",
					"interval"=>$signe . $heures . " h " . $resteMin . " min"
				];
			}else{
				return [
					"retard"=>"oui",
					"interval"=>$signe . $heures . " h " . $resteMin . " min"
				];
			}
        //    return $signe . $heures . " h " . $resteMin . " min";
        }
    } else {
		if($signe=="-"){
			return [
				"retard"=>"non",
				"interval"=>$signe . $minutes . " min"
			];
		}else{
			return [
				"retard"=>"oui",
				"interval"=>$signe . $minutes . " min"
			];
		}
      ///  return $signe . $minutes . " min";
    }
}
function differenceHeure($h1, $h2)
{
    $heure1 = new DateTime($h1);
    $heure2 = new DateTime($h2);

    // Retourne l'heure la plus récente
    if ($heure1 > $heure2) {
        return $heure1->format('H:i:s');
    }

    return $heure2->format('H:i:s');
}
function moisEnFrancais($date)
{
    // Convertir la date en timestamp
    $timestamp = strtotime($date);

    // Tableau des mois en français
    $mois = [
        '01' => 'janvier',
        '02' => 'février',
        '03' => 'mars',
        '04' => 'avril',
        '05' => 'mai',
        '06' => 'juin',
        '07' => 'juillet',
        '08' => 'août',
        '09' => 'septembre',
        '10' => 'octobre',
        '11' => 'novembre',
        '12' => 'décembre'
    ];

    // Récupérer le numéro du mois
    $numMois = date('m', $timestamp);

    // Retourner le mois en français
    return $mois[$numMois];
}
function jourEnFrancais($date)
{
    // Convertir la date en timestamp
    $timestamp = strtotime($date);
	if ($timestamp === false) {
        return "Date invalide";
    }
    // Tableau des jours en français
    $jours = [
        'Monday'    => 'Lundi',
        'Tuesday'   => 'Mardi',
        'Wednesday' => 'Mercredi',
        'Thursday'  => 'Jeudi',
        'Friday'    => 'Vendredi',
        'Saturday'  => 'Samedi',
        'Sunday'    =>  'Dimanche'
    ];

    // Récupérer le jour en anglais
    $jourAnglais = date('l', $timestamp);

  
   return $jours[$jourAnglais];
}
function savoir_cycle($maitricule){
    require 'base.php';
    $stmtadm = $con->prepare("SELECT * FROM affect_ecole WHERE id_enseignant = ?");
        $stmtadm->bind_param("s", $maitricule);
        $stmtadm->execute();
        $resultadm = $stmtadm->get_result();

        if ($resultadm && $resultadm->num_rows === 1) {
            $data = $resultadm->fetch_assoc();
            return $data['cycle'];
        }
        return "Aucun cycle trouvé";
}
function if_admin_or_enseigant($mat){
    require 'base.php';
    $maitricule = trim($mat);

        $stmtadm = $con->prepare("SELECT id FROM administratif WHERE id = ?");
        $stmtadm->bind_param("s", $maitricule);
        $stmtadm->execute();
        $resultadm = $stmtadm->get_result();

        if ($resultadm && $resultadm->num_rows === 1) {
            return "admin";
        }

        $stmtens = $con->prepare("SELECT id FROM enseignant WHERE id = ?");
        $stmtens->bind_param("s", $maitricule);
        $stmtens->execute();
        $resultens = $stmtens->get_result();

        if ($resultens && $resultens->num_rows === 1) {
            return "enseignant";
        }

        return "Aucun membre trouvé";
}
function trouver_annee_et_ecole($maitricule){
    require 'base.php';
    $stmtadm = $con->prepare("SELECT * FROM affect_ecole WHERE id_enseignant = ?");
    $stmtadm->bind_param("s", $maitricule);
    $stmtadm->execute();
    $resultadm = $stmtadm->get_result();
    if ($resultadm && $resultadm->num_rows === 1) {
        $data = $resultadm->fetch_assoc();
        $idecole=$data['ecole'];
        $status='on';
        $stmtannee = $con->prepare("SELECT * FROM annee WHERE ecole = ? and statut=?");
        $stmtannee->bind_param("ss", $idecole,$status);
        $stmtannee->execute();
        $resultanne= $stmtannee->get_result();
        if($resultanne && $resultanne->num_rows === 1){
            $data2 = $resultanne->fetch_assoc();
            $anee=$data2['lib'];
            return[
                "success"=>true,
                "annee"=>$anee,
                "ecole"=>$idecole,
                "message"=>""
            ];
        }else{
            return [
                "success"=>false,
                "message"=>"Année non active"
            ] ;
        }
        
    }else{
        return [
            "success"=>false,
            "message"=>"Aucun enseigant trouvé"
        ] ;
    }
    
}
function trouver_annee_et_ecole_admin($maitricule){
    require 'base.php';
    $stmtadm = $con->prepare("SELECT * FROM administratif WHERE id = ?");
    $stmtadm->bind_param("s", $maitricule);
    $stmtadm->execute();
    $resultadm = $stmtadm->get_result();
    if ($resultadm && $resultadm->num_rows === 1) {
        $data = $resultadm->fetch_assoc();
        $idecole=$data['ecole'];
        $status='on';
        $stmtannee = $con->prepare("SELECT * FROM annee WHERE ecole = ? and statut=?");
        $stmtannee->bind_param("ss", $idecole,$status);
        $stmtannee->execute();
        $resultanne= $stmtannee->get_result();
        if($resultanne && $resultanne->num_rows === 1){
            $data2 = $resultanne->fetch_assoc();
            $anee=$data2['lib'];
            return[
                "success"=>true,
                "annee"=>$anee,
                "ecole"=>$idecole,
                "message"=>""
            ];
        }else{
            return [
                "success"=>false,
                "message"=>"Année non active"
            ] ;
        }
        
    }else{
        return [
            "success"=>false,
            "message"=>"Aucun admin trouvé"
        ] ;
    }
    
}
$datareceive = json_decode($rawJson);
$heure_actuelle = date("H:i:s");
if(is_object($datareceive )){
    
    $data=$datareceive;
    if ($data) {
        $dt = new DateTime($data->timestamp);
        $date  = $dt->format('Y-m-d');
        $heure_depart=$dt->format("H:i:s");
        $harriv=differenceHeure($heure_actuelle,$dt->format("H:i:s"));
        $jour=$dt->format("D");
        $jourA=$dt->format("d");
        $mois=$dt->format("m");
        $mois_francais=moisEnFrancais(($mois));
        $annee=$dt->format("Y");
        $jour_de_la_semaine=jourEnFrancais($date);
         $enseignant_or_admin=$data->external_user_id;
         $timestamp=$data->timestamp;
         $inout=$data->inout;
         if(if_admin_or_enseigant($enseignant_or_admin)=="enseignant"){
            $status= trouver_annee_et_ecole($enseignant_or_admin)['success'];
            $msg= trouver_annee_et_ecole($enseignant_or_admin)['message'];
            if($status){
                $id_ecole= trouver_annee_et_ecole($enseignant_or_admin)['ecole'];
                $annee_encours= trouver_annee_et_ecole($enseignant_or_admin)['annee'];
                if ($inout=='0') {
                    $check=$con->query("SELECT * FROM presence_ens WHERE dat='$date' and matricule='$enseignant_or_admin' AND ecole='$id_ecole' ");
                    $verif=$check->fetch_assoc();
                    if(isset($verif['id'])){
                        $response[] = [
                            "matricule" => $enseignant_or_admin,
                            "action" => mb_convert_encoding("Présence enseigant déjà enregistrée manuellement ou par empreinte, le $jour_de_la_semaine $jourA $mois_francais $annee",'UTF-8', 'auto')
                        ];
                    }else{
                        if(savoir_cycle($enseignant_or_admin)=='SECONDAIRE'){
                            $cycle=savoir_cycle($enseignant_or_admin);
                            $retard="";
                            $interval="";
                            $jour_de_la_semaine=jourEnFrancais($date);
                            $trouver_horraire=$con->query("SELECT * FROM horraire_generale where jours='$jour_de_la_semaine' and id_enseignant='$enseignant_or_admin' and id_ecole='$id_ecole' ");
                            $heure_trouve=$trouver_horraire->fetch_assoc();
                            if(isset($heure_trouve['jours'])){
                                    $heuret=$heure_trouve['heure'];
                                    $trouver_heure_programme=$con->query("SELECT * FROM horraire_programme where heures='$heuret' and ecole='$id_ecole' ");
                                    $heure_debut=$trouver_heure_programme->fetch_assoc();
                                    $retard=ecartHeure($heure_debut['heure_debut'],$harriv)['retard'];
                                    $interval=ecartHeure($heure_debut['heure_debut'],$harriv)['interval'];
                                    $inser=$con->query("INSERT INTO presence_ens (matricule, dat, statut, cycle, heure_arriv, heure_depart, nbr_heur, jour,mois, annee, ecole,users,retard,ecart) VALUES ('$enseignant_or_admin', '$date', 'Présent','$cycle','$harriv','','0','$jour', '$mois', '$annee_encours','$id_ecole','Terminal','$retard','$interval')");
                                    $response[] = [
                                        "matricule" => $enseignant_or_admin,
                                        "action" => "Entree enregistrée"
                                    ];
                            }else{
                                $inser=$con->query("INSERT INTO presence_ens (matricule, dat, statut, cycle, heure_arriv, heure_depart, nbr_heur, jour,mois, annee, ecole,users,retard,ecart) VALUES ('$enseignant_or_admin', '$date', 'OFF','$cycle','$harriv','','0','$jour', '$mois', '$annee_encours','$id_ecole','Terminal','$retard','$interval')");
                                    $response[] = [
                                        "matricule" => $enseignant_or_admin,
                                        "action" => "OFF enregistrée"
                                    ];
                            }
                        }else if(savoir_cycle($enseignant_or_admin)=='PRIMAIRE' or savoir_cycle($enseignant_or_admin)=='MATERNELLE'){
                            $jour_de_la_semaine=jourEnFrancais($date);
                            $cycle=savoir_cycle($enseignant_or_admin);
                            $retard="";
			                $interval="";
                            $trouver_horraire=$con->query("SELECT * FROM heure_programme where jours='$jour_de_la_semaine' and type='$cycle' and ecole='$id_ecole' ");
                            $heure_trouve=$trouver_horraire->fetch_assoc();
                            if(isset($heure_trouve['type'])){
                                $heuret=$heure_trouve['heure_debut'];
                                $retard=ecartHeure($heuret,$harriv)['retard'];
                                $interval=ecartHeure( $heuret,$harriv)['interval'];
                               $inser=$con->query("INSERT INTO presence_ens (matricule, dat, statut, cycle, heure_arriv, heure_depart, nbr_heur, jour,mois, annee, ecole,users,retard,ecart) VALUES ('$enseignant', '$date', 'Présent','$cycle','$harriv','','0','$jour', '$mois', '$annee_encours','$id_ecole','Terminal','$retard','$interval')");
                               $response[] = [
                                    "matricule" => $enseignant_or_admin,
                                    "action" => "Entree enregistrée"
                                ];
                            }else{
                                $inser=$con->query("INSERT INTO presence_ens (matricule, dat, statut, cycle, heure_arriv, heure_depart, nbr_heur, jour,mois, annee, ecole,users,retard,ecart) VALUES ('$enseignant', '$date', 'OFF','$cycle','$harriv','','0','$jour', '$mois', '$annee_encours','$id_ecole','Terminal','$retard','$interval')");
                                $response[] = [
                                    "matricule" => $enseignant_or_admin,
                                    "action" => "OFF enregistrée"
                                ];
                            }
                        }
                    }
                }else {
                    $req_sd=$con->query("SELECT * FROM presence_ens WHERE heure_depart='' AND matricule='$enseignant_or_admin' and dat='$date' and ecole='$id_ecole' ");
                    $data_sd=$req_sd->fetch_assoc();
                    $count=$req_sd->num_rows;
                    if($count==1){
                        $update=$con->query("UPDATE presence_ens SET  heure_depart='$harriv' WHERE matricule='$enseignant_or_admin' and dat='$date' and ecole='$id_ecole'  ");
                        $response[] = [
                            "matricule" => $enseignant_or_admin,
                            "action" => "sortie enregistrée"
                        ];
                    }else{
                        $response[] = [
                            "matricule" => $enseignant_or_admin,
                            "action" => mb_convert_encoding("déjà parti(e)",'UTF-8', 'auto')
                        ];
                    }
                }
            }else{
                $response[] = [
                    "matricule" => $enseignant_or_admin,
                    "action" => $msg
                ];
            }
         }else if(if_admin_or_enseigant($enseignant_or_admin)=="admin"){
            $status= trouver_annee_et_ecole_admin($enseignant_or_admin)['success'];
            $msg= trouver_annee_et_ecole_admin($enseignant_or_admin)['message'];
            if($status){
                $id_ecole= trouver_annee_et_ecole_admin($enseignant_or_admin)['ecole'];
                $annee_encours= trouver_annee_et_ecole_admin($enseignant_or_admin)['annee'];
                if($inout=='0'){
                    $check=$con->query("SELECT * FROM presence_admin WHERE dat='$date' and matricule='$enseignant_or_admin' AND ecole='$id_ecole' ");
                    $verif=$check->fetch_assoc();
                    if(isset($verif['id'])){
                        $response[] = [
                            "matricule" => $enseignant_or_admin,
                           "action" => mb_convert_encoding("Présence administrative déjà enregistrée manuellement ou par empreinte, le $jour_de_la_semaine $jourA $mois_francais $annee",'UTF-8', 'auto')
                        ];
                    }else{
                            $retard="";
			                $interval="";
                            $trouver_horraire=$con->query("SELECT * FROM heure_programme where jours='$jour_de_la_semaine' and type='ADMINISTRATIF' and ecole='$id_ecole' ");
                            $heure_trouve=$trouver_horraire->fetch_assoc();
                            if(isset($heure_trouve['type'])){
                                $heuret=$heure_trouve['heure_debut'];
                                $retard=ecartHeure($heuret,$harriv)['retard'];
                                $interval=ecartHeure( $heuret,$harriv)['interval'];
                               $inser=$con->query("INSERT INTO presence_admin (matricule, dat, statut, heure_arriv, heure_depart, jour,mois, annee, ecole,users,retard,ecart) VALUES ('$enseignant_or_admin', '$date', 'Présent','$harriv','','$jour', '$mois', '$annee_encours','$id_ecole','Terminal','$retard','$interval')");
                               $response[] = [
                                    "matricule" => $enseignant_or_admin,
                                    "action" => "Entree enregistrée"
                                ];
                            }else{
                                $inser=$con->query("INSERT INTO presence_admin (matricule, dat, statut, heure_arriv, heure_depart, jour,mois, annee, ecole,users,retard,ecart) VALUES ('$enseignant_or_admin', '$date', 'OFF','$harriv','','$jour', '$mois', '$annee_encours','$id_ecole','Terminal','$retard','$interval')");
                                $response[] = [
                                    "matricule" => $enseignant_or_admin,
                                    "action" => "OFF enregistrée"
                                ];
                            }
                    }
                }else {
                    $req_sd=$con->query("SELECT * FROM presence_admin WHERE heure_depart='' AND matricule='$enseignant_or_admin' and dat='$date' and ecole='$id_ecole' ");
                    $data_sd=$req_sd->fetch_assoc();
                    $count=$req_sd->num_rows;
                    if($count==1){
                        $update=$con->query("UPDATE presence_admin SET  heure_depart='$harriv' WHERE matricule='$enseignant_or_admin' and dat='$date' and ecole='$id_ecole'  ");
                        $response[] = [
                            "matricule" => $enseignant_or_admin,
                            "action" => "sortie enregistrée"
                        ];
                    }else{
                        $response[] = [
                            "matricule" => $enseignant_or_admin,
                            "action" => mb_convert_encoding("déjà parti(e)",'UTF-8', 'auto')
                        ];
                    }
                }
            }else{
                $response[] = [
                    "matricule" => $enseignant_or_admin,
                    "action" => $msg
                ];
            }
         }
     }else{
        $response[] = [
            "matricule" => $enseignant,
            "action" => "Donnée concoppu"
        ];
     }
}
else if(is_array($datareceive)){
    foreach ($datareceive as $key => $data) {
        if ($data) {
            $dt = new DateTime($data->timestamp);
            $date  = $dt->format('Y-m-d');
            $heure_depart=$dt->format("H:i:s");
          //     $harriv=$dt->format("H:i:s");
            $harriv=differenceHeure($heure_actuelle,$dt->format("H:i:s"));

            $jour=$dt->format("D");
            $mois=$dt->format("m");
            $mois_francais=moisEnFrancais(($mois));
            $annee=$dt->format("Y");
            $jour_de_la_semaine=jourEnFrancais($date);
             $enseignant_or_admin=$data->external_user_id;
             $timestamp=$data->timestamp;
             $inout=$data->inout;
             if(if_admin_or_enseigant($enseignant_or_admin)=="enseignant"){
                $status= trouver_annee_et_ecole($enseignant_or_admin)['success'];
                $msg= trouver_annee_et_ecole($enseignant_or_admin)['message'];
                if($status){
                    $id_ecole= trouver_annee_et_ecole($enseignant_or_admin)['ecole'];
                    $annee_encours= trouver_annee_et_ecole($enseignant_or_admin)['annee'];
                    if ($inout=='0') {
                        $check=$con->query("SELECT * FROM presence_ens WHERE dat='$date' and matricule='$enseignant_or_admin' AND ecole='$id_ecole' ");
                        $verif=$check->fetch_assoc();
                        if(isset($verif['id'])){
                            $response[] = [
                                "matricule" => $enseignant_or_admin,
                                "action" => mb_convert_encoding("Présence enseigant déjà enregistrée manuellement ou par empreinte, le $jour_de_la_semaine $jour $mois_francais $annee",'UTF-8', 'auto')
                            ];
                        }else{
                            if(savoir_cycle($enseignant_or_admin)=='SECONDAIRE'){
                                $cycle=savoir_cycle($enseignant_or_admin);
                                $retard="";
                                $interval="";
                                $jour_de_la_semaine=jourEnFrancais($date);
                                $trouver_horraire=$con->query("SELECT * FROM horraire_generale where jours='$jour_de_la_semaine' and id_enseignant='$enseignant_or_admin' and id_ecole='$id_ecole' ");
                                $heure_trouve=$trouver_horraire->fetch_assoc();
                                if(isset($heure_trouve['jours'])){
                                        $heuret=$heure_trouve['heure'];
                                        $trouver_heure_programme=$con->query("SELECT * FROM horraire_programme where heures='$heuret' and ecole='$id_ecole' ");
                                        $heure_debut=$trouver_heure_programme->fetch_assoc();
                                        $retard=ecartHeure($heure_debut['heure_debut'],$harriv)['retard'];
                                        $interval=ecartHeure($heure_debut['heure_debut'],$harriv)['interval'];
                                        $inser=$con->query("INSERT INTO presence_ens (matricule, dat, statut, cycle, heure_arriv, heure_depart, nbr_heur, jour,mois, annee, ecole,users,retard,ecart) VALUES ('$enseignant_or_admin', '$date', 'Présent','$cycle','$harriv','','0','$jour', '$mois', '$annee_encours','$id_ecole','Terminal','$retard','$interval')");
                                        $response[] = [
                                            "matricule" => $enseignant_or_admin,
                                            "action" => "Entrée enregistrée"
                                        ];
                                }else{
                                    $inser=$con->query("INSERT INTO presence_ens (matricule, dat, statut, cycle, heure_arriv, heure_depart, nbr_heur, jour,mois, annee, ecole,users,retard,ecart) VALUES ('$enseignant_or_admin', '$date', 'OFF','$cycle','$harriv','','0','$jour', '$mois', '$annee_encours','$id_ecole','Terminal','$retard','$interval')");
                                        $response[] = [
                                            "matricule" => $enseignant_or_admin,
                                            "action" => "OFF enregistrée"
                                        ];
                                }
                            }else if(savoir_cycle($enseignant_or_admin)=='PRIMAIRE' or savoir_cycle($enseignant_or_admin)=='MATERNELLE'){
                                $jour_de_la_semaine=jourEnFrancais($date);
                                $cycle=savoir_cycle($enseignant_or_admin);
                                $retard="";
                                $interval="";
                                $trouver_horraire=$con->query("SELECT * FROM heure_programme where jours='$jour_de_la_semaine' and type='$cycle' and ecole='$id_ecole' ");
                                $heure_trouve=$trouver_horraire->fetch_assoc();
                                if(isset($heure_trouve['type'])){
                                    $heuret=$heure_trouve['heure_debut'];
                                    $retard=ecartHeure($heuret,$harriv)['retard'];
                                    $interval=ecartHeure( $heuret,$harriv)['interval'];
                                   $inser=$con->query("INSERT INTO presence_ens (matricule, dat, statut, cycle, heure_arriv, heure_depart, nbr_heur, jour,mois, annee, ecole,users,retard,ecart) VALUES ('$enseignant', '$date', 'Présent','$cycle','$harriv','','0','$jour', '$mois', '$annee_encours','$id_ecole','Terminal','$retard','$interval')");
                                   $response[] = [
                                        "matricule" => $enseignant_or_admin,
                                        "action" => "Entrée enregistrée"
                                    ];
                                }else{
                                    $inser=$con->query("INSERT INTO presence_ens (matricule, dat, statut, cycle, heure_arriv, heure_depart, nbr_heur, jour,mois, annee, ecole,users,retard,ecart) VALUES ('$enseignant', '$date', 'OFF','$cycle','$harriv','','0','$jour', '$mois', '$annee_encours','$id_ecole','Terminal','$retard','$interval')");
                                    $response[] = [
                                        "matricule" => $enseignant_or_admin,
                                        "action" => "OFF enregistrée"
                                    ];
                                }
                            }
                        }
                    }else {
                        $req_sd=$con->query("SELECT * FROM presence_ens WHERE heure_depart='' AND matricule='$enseignant_or_admin' and dat='$date' and ecole='$id_ecole' ");
                        $data_sd=$req_sd->fetch_assoc();
                        $count=$req_sd->num_rows;
                        if($count==1){
                            $update=$con->query("UPDATE presence_ens SET  heure_depart='$harriv' WHERE matricule='$enseignant_or_admin' and dat='$date' and ecole='$id_ecole'  ");
                            $response[] = [
                                "matricule" => $enseignant_or_admin,
                                "action" => "sortie enregistrée"
                            ];
                        }else{
                            $response[] = [
                                "matricule" => $enseignant_or_admin,
                                "action" => mb_convert_encoding("déjà parti(e)",'UTF-8', 'auto')
                            ];
                        }
                    }
                }else{
                    $response[] = [
                        "matricule" => $enseignant_or_admin,
                        "action" => $msg
                    ];
                }
             }else if(if_admin_or_enseigant($enseignant_or_admin)=="admin"){
                $status= trouver_annee_et_ecole_admin($enseignant_or_admin)['success'];
                $msg= trouver_annee_et_ecole_admin($enseignant_or_admin)['message'];
                if($status){
                    $id_ecole= trouver_annee_et_ecole_admin($enseignant_or_admin)['ecole'];
                    $annee_encours= trouver_annee_et_ecole_admin($enseignant_or_admin)['annee'];
                    if($inout=='0'){
                        $check=$con->query("SELECT * FROM presence_admin WHERE dat='$date' and matricule='$enseignant_or_admin' AND ecole='$id_ecole' ");
                        $verif=$check->fetch_assoc();
                        if(isset($verif['id'])){
                            $response[] = [
                                "matricule" => $enseignant_or_admin,
                               "action" => mb_convert_encoding("Présence administratif déjà enregistrée manuellement ou par empreinte, le $jour_de_la_semaine $jour $mois_francais $annee",'UTF-8', 'auto')
                            ];
                        }else{
                                $retard="";
                                $interval="";
                                $trouver_horraire=$con->query("SELECT * FROM heure_programme where jours='$jour_de_la_semaine' and type='ADMINISTRATIF' and ecole='$id_ecole' ");
                                $heure_trouve=$trouver_horraire->fetch_assoc();
                                
                                if(isset($heure_trouve['type'])){
                                    $heuret=$heure_trouve['heure_debut'];
                                    $retard=ecartHeure($heuret,$harriv)['retard'];
                                    $interval=ecartHeure( $heuret,$harriv)['interval'];
                                   $inser=$con->query("INSERT INTO presence_admin (matricule, dat, statut, heure_arriv, heure_depart, jour,mois, annee, ecole,users,retard,ecart) VALUES ('$enseignant_or_admin', '$date', 'Présent','$harriv','','$jour', '$mois', '$annee_encours','$id_ecole','Terminal','$retard','$interval')");
                                   $response[] = [
                                        "matricule" => $enseignant_or_admin,
                                        "action" => "Entreé enregistrée"
                                    ];
                                }else{
                                    $inser=$con->query("INSERT INTO presence_admin (matricule, dat, statut, heure_arriv, heure_depart, jour,mois, annee, ecole,users,retard,ecart) VALUES ('$enseignant_or_admin', '$date', 'OFF','$harriv','','$jour', '$mois', '$annee_encours','$id_ecole','Terminal','$retard','$interval')");
                                    $response[] = [
                                        "matricule" => $enseignant_or_admin,
                                        "action" => "Off enregistrée"
                                    ];
                                }
                        }
                    }else {
                        $req_sd=$con->query("SELECT * FROM presence_admin WHERE heure_depart='' AND matricule='$enseignant_or_admin' and dat='$date' and ecole='$id_ecole' ");
                        $data_sd=$req_sd->fetch_assoc();
                        $count=$req_sd->num_rows;
                        if($count==1){
                            $update=$con->query("UPDATE presence_admin SET  heure_depart='$harriv' WHERE matricule='$enseignant_or_admin' and dat='$date' and ecole='$id_ecole'  ");
                            $response[] = [
                                "matricule" => $enseignant_or_admin,
                                "action" => "sortie enregistrée"
                            ];
                        }else{
                            $response[] = [
                                "matricule" => $enseignant_or_admin,
                                "action" => mb_convert_encoding("déjà parti(e)",'UTF-8', 'auto')
                            ];
                        }
                    }
                }else{
                    $response[] = [
                        "matricule" => $enseignant_or_admin,
                        "action" => $msg
                    ];
                }
             }
         }else{
            $response[] = [
                "matricule" => $enseignant_or_admin,
                "action" => "Donnée concoppu"
            ];
         }
         
    }
}
//header('Content-Type: text/html; charset=UTF-8');//
echo json_encode([
    "success" => true,
    "processed" => count($response),
    "details" => $response
], JSON_PRETTY_PRINT);

///http://localhost/sygie/data_recev.php

///{"nom":"omas","postnom":"omas","prenom":"omas"}
// Utiliser les données
///http://localhost/sygie/API/login.php


/*


Admin
{
      "log_id": 60,
      "terminal_sn": "ZYTJ20128569",
      "enrollid": 5,
      "external_user_id": "EMP005",
      "user_name": "Nelson Kayisi",
      "timestamp": "2026-01-05T13:14:47+00:00",
      "mode": 1,
      "inout": 0,
      "event": 0,
      "temperature": null,
      "access_granted": true,
      "metadata": {
        "mode": 1,
        "temp": null,
        "time": "2026-01-05 13:14:47",
        "event": 0,
        "inout": 0,
        "enrollid": 5,
        "verifymode": null
      },
      "received_at": "2026-01-05T13:15:00.063Z",
      "source": "tm20_biometric"
}

ensei
{
      "log_id": 60,
      "terminal_sn": "ZYTJ20128569",
      "enrollid": 5,
      "external_user_id": "MU4338",
      "user_name": "Nelson Kayisi",
      "timestamp": "2026-01-05T13:14:47+00:00",
      "mode": 1,
      "inout": 0,
      "event": 0,
      "temperature": null,
      "access_granted": true,
      "metadata": {
        "mode": 1,
        "temp": null,
        "time": "2026-01-05 13:14:47",
        "event": 0,
        "inout": 0,
        "enrollid": 5,
        "verifymode": null
      },
      "received_at": "2026-01-05T13:15:00.063Z",
      "source": "tm20_biometric"
}

*/




?>