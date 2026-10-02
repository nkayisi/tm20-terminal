"""
Service de génération de rapports d'entrée/sortie
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from django.db.models import Q, Count, Max, Min
from django.utils import timezone

from ..models import AttendanceLog, BiometricUser, Terminal

logger = logging.getLogger(__name__)


class AttendanceReportService:
    """
    Service pour générer des rapports d'entrée/sortie clairs et structurés
    """
    
    @staticmethod
    def get_daily_attendance_summary(
        terminal: Optional[Terminal] = None,
        date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Génère un résumé quotidien des entrées/sorties par utilisateur.
        
        Args:
            terminal: Terminal spécifique (optionnel)
            date: Date du rapport (défaut: aujourd'hui)
        
        Returns:
            Liste de dictionnaires avec les données d'entrée/sortie
        """
        if not date:
            date = timezone.localdate()
        
        # Récupérer tous les logs du jour
        logs_queryset = AttendanceLog.objects.filter(
            time__date=date
        ).select_related('user', 'terminal')
        
        if terminal:
            logs_queryset = logs_queryset.filter(terminal=terminal)
        
        logs_queryset = logs_queryset.order_by('enrollid', 'time')
        
        # Grouper par utilisateur
        user_attendance = {}
        
        for log in logs_queryset:
            enrollid = log.enrollid
            
            if enrollid not in user_attendance:
                user_attendance[enrollid] = {
                    'enrollid': enrollid,
                    'user_name': log.user.name if log.user else f"User {enrollid}",
                    'terminal_sn': log.terminal.sn,
                    'entries': [],
                    'exits': [],
                    'total_entries': 0,
                    'total_exits': 0,
                    'first_entry': None,
                    'last_exit': None,
                    'is_currently_inside': False,
                }
            
            if log.is_entry:
                user_attendance[enrollid]['entries'].append({
                    'time': log.time,
                    'mode': log.get_mode_display(),
                })
                user_attendance[enrollid]['total_entries'] += 1
                
                if not user_attendance[enrollid]['first_entry']:
                    user_attendance[enrollid]['first_entry'] = log.time
            else:
                user_attendance[enrollid]['exits'].append({
                    'time': log.time,
                    'mode': log.get_mode_display(),
                })
                user_attendance[enrollid]['total_exits'] += 1
                user_attendance[enrollid]['last_exit'] = log.time
        
        # Déterminer si l'utilisateur est actuellement à l'intérieur
        for enrollid, data in user_attendance.items():
            data['is_currently_inside'] = data['total_entries'] > data['total_exits']
        
        return list(user_attendance.values())
    
    @staticmethod
    def get_user_attendance_history(
        enrollid: int,
        terminal: Terminal,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Récupère l'historique complet des entrées/sorties d'un utilisateur.
        
        Args:
            enrollid: ID d'enrôlement de l'utilisateur
            terminal: Terminal
            start_date: Date de début (optionnel)
            end_date: Date de fin (optionnel)
            limit: Nombre maximum de résultats
        
        Returns:
            Liste des pointages avec statut clair
        """
        queryset = AttendanceLog.objects.filter(
            enrollid=enrollid,
            terminal=terminal
        ).select_related('user')
        
        if start_date:
            queryset = queryset.filter(time__gte=start_date)
        if end_date:
            queryset = queryset.filter(time__lte=end_date)
        
        queryset = queryset.order_by('-time')[:limit]
        
        return [
            {
                'id': log.id,
                'time': log.time,
                'type': 'Entrée' if log.is_entry else 'Sortie',
                'type_code': log.inout,
                'icon': '🟢' if log.is_entry else '🔴',
                'mode': log.get_mode_display(),
                'access_granted': log.access_granted,
                'sync_status': log.sync_status,
            }
            for log in queryset
        ]
    
    @staticmethod
    def get_attendance_statistics(
        terminal: Optional[Terminal] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """
        Génère des statistiques sur les entrées/sorties.
        
        Args:
            terminal: Terminal spécifique (optionnel)
            start_date: Date de début (optionnel)
            end_date: Date de fin (optionnel)
        
        Returns:
            Dictionnaire avec les statistiques
        """
        queryset = AttendanceLog.objects.all()
        
        if terminal:
            queryset = queryset.filter(terminal=terminal)
        if start_date:
            queryset = queryset.filter(time__gte=start_date)
        if end_date:
            queryset = queryset.filter(time__lte=end_date)
        
        total_logs = queryset.count()
        total_entries = queryset.filter(inout=0).count()
        total_exits = queryset.filter(inout=1).count()
        
        unique_users = queryset.values('enrollid').distinct().count()
        
        # Utilisateurs actuellement à l'intérieur (plus d'entrées que de sorties)
        users_inside = 0
        for enrollid in queryset.values_list('enrollid', flat=True).distinct():
            user_logs = queryset.filter(enrollid=enrollid).order_by('-time')
            if user_logs.exists() and user_logs.first().inout == 0:
                users_inside += 1
        
        return {
            'total_logs': total_logs,
            'total_entries': total_entries,
            'total_exits': total_exits,
            'unique_users': unique_users,
            'users_currently_inside': users_inside,
            'entry_exit_balance': total_entries - total_exits,
        }
    
    @staticmethod
    def validate_attendance_consistency(
        terminal: Terminal,
        date: Optional[datetime] = None
    ) -> Dict:
        """
        Valide la cohérence des entrées/sorties (détecte les anomalies).
        
        Args:
            terminal: Terminal à vérifier
            date: Date à vérifier (défaut: aujourd'hui)
        
        Returns:
            Dictionnaire avec les anomalies détectées
        """
        if not date:
            date = timezone.localdate()
        
        logs = AttendanceLog.objects.filter(
            terminal=terminal,
            time__date=date
        ).order_by('enrollid', 'time')
        
        anomalies = []
        user_sequences = {}
        
        for log in logs:
            enrollid = log.enrollid
            
            if enrollid not in user_sequences:
                user_sequences[enrollid] = []
            
            user_sequences[enrollid].append({
                'time': log.time,
                'inout': log.inout,
                'log_id': log.id,
            })
        
        # Vérifier les séquences
        for enrollid, sequence in user_sequences.items():
            for i in range(len(sequence) - 1):
                current = sequence[i]
                next_log = sequence[i + 1]
                
                # Deux entrées consécutives ou deux sorties consécutives = anomalie
                if current['inout'] == next_log['inout']:
                    anomalies.append({
                        'enrollid': enrollid,
                        'type': 'duplicate_' + ('entry' if current['inout'] == 0 else 'exit'),
                        'description': f"Deux {'entrées' if current['inout'] == 0 else 'sorties'} consécutives",
                        'time1': current['time'],
                        'time2': next_log['time'],
                        'log_ids': [current['log_id'], next_log['log_id']],
                    })
        
        return {
            'date': date,
            'terminal_sn': terminal.sn,
            'total_anomalies': len(anomalies),
            'anomalies': anomalies,
            'is_consistent': len(anomalies) == 0,
        }


# Instance par défaut
attendance_report_service = AttendanceReportService()
