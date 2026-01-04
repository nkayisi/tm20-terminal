"""
Service de gestion des horaires de terminaux
"""

import logging
from datetime import date, time, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from django.utils import timezone
from django.db.models import Q

from ..models import Terminal, TerminalSchedule

logger = logging.getLogger('devices.schedule_manager')


class ScheduleManager:
    """Gestionnaire des horaires de terminaux"""
    
    @staticmethod
    async def get_active_schedule(
        terminal: Terminal,
        weekday: Optional[int] = None,
        check_date: Optional[date] = None
    ) -> Optional[TerminalSchedule]:
        """
        Récupère l'horaire actif pour un terminal à une date donnée
        
        Args:
            terminal: Terminal concerné
            weekday: Jour de la semaine (0=Lundi, 6=Dimanche)
            check_date: Date à vérifier (par défaut aujourd'hui)
        
        Returns:
            TerminalSchedule ou None
        """
        if check_date is None:
            check_date = date.today()
        
        if weekday is None:
            weekday = check_date.weekday()
        
        query = TerminalSchedule.objects.filter(
            terminal=terminal,
            weekday=weekday,
            is_active=True
        )
        
        query = query.filter(
            Q(effective_from__isnull=True) | Q(effective_from__lte=check_date)
        ).filter(
            Q(effective_until__isnull=True) | Q(effective_until__gte=check_date)
        )
        
        schedule = await query.order_by('-created_at').afirst()
        
        return schedule
    
    @staticmethod
    async def get_week_schedules(terminal: Terminal) -> Dict[int, TerminalSchedule]:
        """
        Récupère tous les horaires actifs de la semaine pour un terminal
        
        Returns:
            Dict[weekday, TerminalSchedule]
        """
        today = date.today()
        
        schedules = {}
        
        for weekday in range(7):
            schedule = await ScheduleManager.get_active_schedule(
                terminal,
                weekday=weekday,
                check_date=today
            )
            if schedule:
                schedules[weekday] = schedule
        
        return schedules
    
    @staticmethod
    async def create_schedule(
        terminal: Terminal,
        weekday: int,
        check_in_time: time,
        check_out_time: time,
        break_start_time: Optional[time] = None,
        break_end_time: Optional[time] = None,
        tolerance_minutes: int = 15,
        name: str = "",
        effective_from: Optional[date] = None,
        effective_until: Optional[date] = None
    ) -> TerminalSchedule:
        """
        Crée un nouvel horaire pour un terminal
        
        Returns:
            TerminalSchedule créé
        """
        if not name:
            weekday_names = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
            name = f"Horaire {weekday_names[weekday]}"
        
        schedule = await TerminalSchedule.objects.acreate(
            terminal=terminal,
            name=name,
            weekday=weekday,
            check_in_time=check_in_time,
            check_out_time=check_out_time,
            break_start_time=break_start_time,
            break_end_time=break_end_time,
            tolerance_minutes=tolerance_minutes,
            effective_from=effective_from,
            effective_until=effective_until,
            is_active=True
        )
        
        logger.info(f"Horaire créé: {schedule}")
        
        return schedule
    
    @staticmethod
    async def update_schedule(
        schedule_id: int,
        **kwargs
    ) -> Optional[TerminalSchedule]:
        """
        Met à jour un horaire existant
        
        Returns:
            TerminalSchedule mis à jour ou None
        """
        try:
            schedule = await TerminalSchedule.objects.aget(id=schedule_id)
            
            for key, value in kwargs.items():
                if hasattr(schedule, key):
                    setattr(schedule, key, value)
            
            await schedule.asave()
            
            logger.info(f"Horaire mis à jour: {schedule}")
            
            return schedule
            
        except TerminalSchedule.DoesNotExist:
            logger.error(f"Horaire {schedule_id} introuvable")
            return None
    
    @staticmethod
    async def delete_schedule(schedule_id: int) -> bool:
        """
        Supprime un horaire (soft delete en désactivant)
        
        Returns:
            True si succès, False sinon
        """
        try:
            schedule = await TerminalSchedule.objects.aget(id=schedule_id)
            schedule.is_active = False
            await schedule.asave()
            
            logger.info(f"Horaire désactivé: {schedule}")
            
            return True
            
        except TerminalSchedule.DoesNotExist:
            logger.error(f"Horaire {schedule_id} introuvable")
            return False
    
    @staticmethod
    async def sync_schedule_to_terminal(
        terminal: Terminal,
        schedule: TerminalSchedule
    ) -> Tuple[bool, Optional[str]]:
        """
        Synchronise un horaire vers le terminal physique
        
        Note: Cette fonction envoie les horaires au terminal via commande WebSocket
        Le format exact dépend du protocole TM20
        
        Returns:
            Tuple[success, error_message]
        """
        from ..services.commands import CommandService
        from ..core.device_manager import DeviceManager
        
        device_manager = DeviceManager.get_instance()
        
        if not await device_manager.is_connected(terminal.sn):
            return False, f"Terminal {terminal.sn} non connecté"
        
        command_service = CommandService()
        
        try:
            result = await command_service.send_command(
                terminal.sn,
                'setschedule',
                {
                    'weekday': schedule.weekday,
                    'check_in': schedule.check_in_time.strftime('%H:%M'),
                    'check_out': schedule.check_out_time.strftime('%H:%M'),
                    'break_start': schedule.break_start_time.strftime('%H:%M') if schedule.break_start_time else None,
                    'break_end': schedule.break_end_time.strftime('%H:%M') if schedule.break_end_time else None,
                    'tolerance': schedule.tolerance_minutes,
                }
            )
            
            if result.get('success'):
                logger.info(f"Horaire synchronisé vers {terminal.sn}: {schedule}")
                return True, None
            else:
                error = result.get('error', 'Erreur inconnue')
                logger.error(f"Échec synchronisation horaire vers {terminal.sn}: {error}")
                return False, error
                
        except Exception as e:
            error = f"Exception lors de la synchronisation: {str(e)}"
            logger.exception(error)
            return False, error
    
    @staticmethod
    async def sync_all_schedules_to_terminal(terminal: Terminal) -> Tuple[int, int]:
        """
        Synchronise tous les horaires actifs vers le terminal
        
        Returns:
            Tuple[success_count, failed_count]
        """
        schedules = await ScheduleManager.get_week_schedules(terminal)
        
        success_count = 0
        failed_count = 0
        
        for weekday, schedule in schedules.items():
            success, error = await ScheduleManager.sync_schedule_to_terminal(
                terminal,
                schedule
            )
            
            if success:
                success_count += 1
            else:
                failed_count += 1
        
        logger.info(
            f"Synchronisation horaires pour {terminal.sn}: "
            f"{success_count} succès, {failed_count} échecs"
        )
        
        return success_count, failed_count
    
    @staticmethod
    def check_attendance_compliance(
        attendance_time: datetime,
        schedule: TerminalSchedule,
        is_check_in: bool = True
    ) -> Dict[str, any]:
        """
        Vérifie la conformité d'un pointage par rapport à l'horaire
        
        Args:
            attendance_time: Heure du pointage
            schedule: Horaire de référence
            is_check_in: True pour arrivée, False pour sortie
        
        Returns:
            Dict avec status, delay_minutes, is_late, etc.
        """
        attendance_time_only = attendance_time.time()
        
        if is_check_in:
            expected_time = schedule.check_in_time
        else:
            expected_time = schedule.check_out_time
        
        expected_datetime = datetime.combine(attendance_time.date(), expected_time)
        actual_datetime = datetime.combine(attendance_time.date(), attendance_time_only)
        
        delay_minutes = int((actual_datetime - expected_datetime).total_seconds() / 60)
        
        is_late = delay_minutes > schedule.tolerance_minutes
        is_early = delay_minutes < -schedule.tolerance_minutes
        is_on_time = abs(delay_minutes) <= schedule.tolerance_minutes
        
        status = 'on_time'
        if is_late:
            status = 'late'
        elif is_early:
            status = 'early'
        
        return {
            'status': status,
            'delay_minutes': delay_minutes,
            'is_late': is_late,
            'is_early': is_early,
            'is_on_time': is_on_time,
            'expected_time': expected_time,
            'actual_time': attendance_time_only,
            'tolerance_minutes': schedule.tolerance_minutes,
        }
    
    @staticmethod
    async def get_schedule_summary(terminal: Terminal) -> Dict:
        """
        Récupère un résumé des horaires configurés pour un terminal
        
        Returns:
            Dict avec statistiques et informations
        """
        total_schedules = await TerminalSchedule.objects.filter(
            terminal=terminal
        ).acount()
        
        active_schedules = await TerminalSchedule.objects.filter(
            terminal=terminal,
            is_active=True
        ).acount()
        
        week_schedules = await ScheduleManager.get_week_schedules(terminal)
        
        coverage = {
            'total_days': 7,
            'configured_days': len(week_schedules),
            'missing_days': 7 - len(week_schedules),
            'coverage_percentage': (len(week_schedules) / 7) * 100
        }
        
        return {
            'terminal_sn': terminal.sn,
            'total_schedules': total_schedules,
            'active_schedules': active_schedules,
            'week_coverage': coverage,
            'schedules_by_day': {
                weekday: {
                    'name': schedule.name,
                    'check_in': schedule.check_in_time.strftime('%H:%M'),
                    'check_out': schedule.check_out_time.strftime('%H:%M'),
                    'has_break': schedule.break_start_time is not None,
                }
                for weekday, schedule in week_schedules.items()
            }
        }
