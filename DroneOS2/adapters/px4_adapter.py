import asyncio
from typing import Optional
from DroneOS.core.interfaces import IFlightController
from DroneOS.shared.config.models import FlightConfig
from DroneOS.shared.utils.logger import setup_logger
from DroneOS.shared.protocol.messages import TelemetryData

logger = setup_logger("PX4Adapter")

try:
    from mavsdk import System
    from mavsdk.offboard import VelocityBodyYawspeed
except ImportError:
    logger.warning("MAVSDK module not found. Adapter will fail if instantiated without a mock.")
    System = None
    VelocityBodyYawspeed = None

class PX4FlightController(IFlightController):
    """
    Implements IFlightController using MAVSDK for PX4 / Real Drone compatibility.
    This replaces AirSim seamlessly because it adheres to the IFlightController interface.
    """
    def __init__(self, vehicle_name: str, config: FlightConfig):
        self.vehicle_name = vehicle_name
        self.config = config
        self.client: Optional['System'] = None
        self._connected = False
        self._telemetry = self._empty_telemetry()
        self._active_tasks = set()
        self._injections = {}  # Store active TEST_INJECT states

    async def connect(self) -> bool:
        if not System:
            logger.error("Cannot connect to PX4: MAVSDK is not installed.")
            return False

        import glob
        import os
        import signal
        import psutil
        import re
        
        def kill_orphaned_mavsdk(target_conn: str):
            try:
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    if proc.info['name'] and 'mavsdk_server' in proc.info['name']:
                        cmdline = proc.info.get('cmdline', [])
                        if cmdline and any(target_conn in arg for arg in cmdline):
                            logger.info(f"Killing orphaned mavsdk_server (PID {proc.info['pid']}) for {target_conn}")
                            proc.kill()
            except Exception as e:
                logger.warning(f"Failed to kill orphaned MAVSDK server: {e}")

        while not self._connected:
            conn_str = self.config.px4_connection_string

            if conn_str.startswith("serial://auto:"):
                baud = conn_str.split(":")[-1]
                device = None
                while not device:
                    by_id_paths = sorted(glob.glob("/dev/serial/by-id/*"))
                    acm_paths = sorted(glob.glob("/dev/ttyACM*"))
                    usb_paths = sorted(glob.glob("/dev/ttyUSB*"))
                    
                    match = re.search(r'\d+', self.vehicle_name)
                    idx = (int(match.group()) - 1) if match else 0
                    
                    if by_id_paths and len(by_id_paths) > idx:
                        device = by_id_paths[idx]
                    elif acm_paths and len(acm_paths) > idx:
                        device = acm_paths[idx]
                    elif usb_paths and len(usb_paths) > idx:
                        device = usb_paths[idx]
                    elif by_id_paths:
                        device = by_id_paths[-1] # Fallback
                        
                    if device:
                        conn_str = f"serial://{device}:{baud}"
                        break
                    else:
                        logger.info("PX4 DEVICE WAITING")
                        await asyncio.sleep(2.0)
            
            kill_orphaned_mavsdk(conn_str)
            # Recreate System to ensure it spawns a fresh mavsdk_server if it previously failed
            self.client = System()

            logger.info(f"PX4 CONNECTING to {conn_str}")
            try:
                # Wrap connect in a timeout to prevent hanging forever
                await asyncio.wait_for(self.client.connect(system_address=conn_str), timeout=10.0)
                
                async def wait_for_connection():
                    async for state in self.client.core.connection_state():
                        if state.is_connected:
                            return True
                    return False
                
                # Wrap connection state in a timeout as well
                is_connected = await asyncio.wait_for(wait_for_connection(), timeout=15.0)
                if is_connected:
                    logger.info("PX4 CONNECTED")
                    self._connected = True
                    break
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"Connection attempt failed ({type(e).__name__}). Retrying in 5s...")
                await asyncio.sleep(5.0)
                
        self._connected = True
        
        # Request required MAVLink telemetry streams safely
        async def safe_set_rate(method_name, rate):
            if hasattr(self.client.telemetry, method_name):
                try:
                    await getattr(self.client.telemetry, method_name)(rate)
                except Exception as e:
                    logger.warning(f"Optional telemetry rate {method_name} failed: {e}")
            else:
                logger.warning(f"Telemetry API {method_name} not supported by this MAVSDK version.")

        await safe_set_rate('set_rate_position', 5.0)
        await safe_set_rate('set_rate_gps_info', 5.0)
        await safe_set_rate('set_rate_battery', 1.0)
        await safe_set_rate('set_rate_attitude', 5.0)
        logger.info("MAVLink telemetry rate initialization completed.")
        
        # Start background telemetry subscriptions
        t1 = asyncio.create_task(self._subscribe_position())
        t2 = asyncio.create_task(self._subscribe_velocity())
        t3 = asyncio.create_task(self._subscribe_battery())
        t4 = asyncio.create_task(self._subscribe_flight_mode())
        t5 = asyncio.create_task(self._subscribe_gps_info())
        t6 = asyncio.create_task(self._subscribe_armed())
        t7 = asyncio.create_task(self._subscribe_attitude())
        t8 = asyncio.create_task(self._subscribe_health())
        t9 = asyncio.create_task(self._subscribe_status_text())

        self._active_tasks.update([t1, t2, t3, t4, t5, t6, t7, t8, t9])
        
        return True

    async def disconnect(self) -> None:
        self._connected = False
        for task in self._active_tasks:
            task.cancel()
        self._active_tasks.clear()
        self.client = None
        logger.info("PX4 DISCONNECTED")

    async def arm(self) -> bool:
        if not self._connected: return False
        try:
            await self.client.action.arm()
            return True
        except Exception as e:
            if "ActionError" in str(type(e)):
                raise RuntimeError(f"Pixhawk rejected ARM request: {e}")
            raise RuntimeError(f"PX4 Arm failed: {e}")

    async def disarm(self) -> bool:
        if not self._connected: return False
        try:
            await self.client.action.disarm()
            return True
        except Exception as e:
            logger.exception(f"PX4 Disarm failed: {e}")
            return False

    async def takeoff(self, altitude: float = 10.0) -> bool:
        if not self._connected: return False
        try:
            await self.client.action.set_takeoff_altitude(altitude)
            await self.client.action.takeoff()
            return True
        except Exception as e:
            if "ActionError" in str(type(e)):
                raise RuntimeError(f"Pixhawk rejected TAKEOFF request: {e}")
            raise RuntimeError(f"PX4 Takeoff failed: {e}")

    async def land(self) -> bool:
        if not self._connected: return False
        try:
            await self.client.action.land()
            return True
        except Exception as e:
            logger.exception(f"PX4 Land failed: {e}")
            return False

    async def rtl(self) -> bool:
        if not self._connected: return False
        if not self._telemetry.home_valid:
            logger.warning("PX4 RTL rejected: Home position invalid")
            return False
        try:
            await self.client.action.return_to_launch()
            return True
        except Exception as e:
            if "ActionError" in str(type(e)):
                raise RuntimeError(f"Pixhawk rejected RTL request: {e}")
            logger.exception(f"PX4 RTL failed: {e}")
            return False

    async def hover(self) -> bool:
        if not self._connected: return False
        try:
            await self.client.action.hold()
            return True
        except (OSError, RuntimeError) as e:
            logger.exception(f"PX4 Hover failed: {e}")
            return False
            
    async def kill(self) -> bool:
        if not self._connected: return False
        try:
            await self.client.action.kill()
            return True
        except Exception as e:
            logger.exception(f"PX4 Kill failed: {e}")
            return False

    async def goto_location(self, lat: float, lon: float, alt: float, yaw: float = 0.0) -> bool:
        if not self._connected: return False
        try:
            await self.client.action.goto_location(lat, lon, alt, yaw)
            return True
        except Exception as e:
            logger.exception(f"PX4 Goto Location failed: {e}")
            return False

    async def move_velocity(self, vx: float, vy: float, vz: float, duration: float, yaw_rate: float = 0.0) -> bool:
        if not self._connected: return False
        
        telemetry = await self.get_telemetry()
        mode_upper = telemetry.flight_mode.upper() if telemetry.flight_mode else ""
        
        # Determine if we should use offboard or manual_control
        use_manual = (not telemetry.gps_valid) or (mode_upper in ["ALTCTL", "MANUAL", "STABILIZED"])

        try:
            if use_manual:
                # Normalize inputs for manual_control
                pitch = max(-1.0, min(1.0, vx / 5.0))
                roll = max(-1.0, min(1.0, vy / 5.0))
                throttle = max(-1.0, min(1.0, -vz / 3.0)) # vz is NED (positive down), throttle is positive up
                yaw = max(-1.0, min(1.0, yaw_rate / 90.0))
                
                await self.client.manual_control.set_manual_control_input(pitch, roll, throttle, yaw)
                await asyncio.sleep(duration)
                return True
            else:
                # Offboard requires valid GPS
                await self.client.offboard.set_velocity_body(
                    VelocityBodyYawspeed(vx, vy, vz, yaw_rate)
                )
                try:
                    await self.client.offboard.start()
                except Exception as e:
                    logger.debug(f"Offboard start failed or already active: {e}")
                await asyncio.sleep(duration)
                return True
        except (OSError, RuntimeError) as e:
            logger.exception(f"PX4 Move failed: {e}")
            return False
        finally:
            if self._connected:
                try:
                    if use_manual:
                        # Neutral command
                        await self.client.manual_control.set_manual_control_input(0.0, 0.0, 0.0, 0.0)
                    else:
                        # Guarantee neutral command on exit/cancel
                        await self.client.offboard.set_velocity_body(
                            VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)
                        )
                        await self.client.offboard.stop()
                except Exception as e:
                    logger.error(f"Failed to cleanly terminate move stream: {e}")

    async def set_mode(self, mode: str) -> bool:
        if not self._connected:
            raise RuntimeError("Not connected")
        mode_upper = mode.upper()
        
        try:
            if mode_upper == "RTL":
                await self.client.action.return_to_launch()
            elif mode_upper == "LAND":
                await self.client.action.land()
            elif mode_upper == "LOITER" or mode_upper == "HOLD":
                await self.client.action.hold()
            elif mode_upper == "ALTCTL":
                await self.client.manual_control.start_altitude_control()
            elif mode_upper == "MANUAL":
                # Fallback to altitude control for manual without GPS
                await self.client.manual_control.start_altitude_control()
            else:
                # Based on audit, MAVSDK-Python action class in this environment
                # does NOT expose set_custom_mode. We cannot fake it.
                raise RuntimeError(f"Mode {mode} is not supported by the current flight-control interface.")
            
            # Verify mode change via telemetry
            for _ in range(10):
                import asyncio
                await asyncio.sleep(0.1)
                t = await self.get_telemetry()
                if t.flight_mode and mode_upper in t.flight_mode.upper():
                    return True
                    
            logger.warning(f"Mode command sent, but telemetry didn't confirm {mode} within 1 second.")
            return True # Command didn't error, just UI might not show it yet.
            
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise e
            raise RuntimeError(f"PX4 Set Mode failed: {e}")

    def set_test_injection(self, injection_type: str, active: bool):
        self._injections[injection_type] = active
        if active:
            logger.warning(f"TEST INJECTION ACTIVE: {injection_type}")

    async def get_telemetry(self) -> TelemetryData:
        # Create a deep copy of telemetry so we don't permanently corrupt internal state
        import copy
        t = copy.deepcopy(self._telemetry)
        
        # Track which injections are active so UI can explicitly distinguish fake data
        t.active_injections = [k for k, v in self._injections.items() if v]

        # Apply active injections
        if self._injections.get("GPS_LOST"):
            t.gps_valid = False
            t.latitude = None
            t.longitude = None
        if self._injections.get("BATTERY_LOW"):
            t.battery_level = 15.0
        if self._injections.get("BATTERY_CRITICAL"):
            t.battery_level = 5.0
        if self._injections.get("TELEMETRY_STALE"):
            # push timestamp back by 10 seconds to simulate stall
            if t.timestamp:
                t.timestamp -= 10.0
                
        return t

    def _mark_telemetry_fresh(self):
        import time
        self._telemetry.timestamp = time.time()

    async def _subscribe_position(self):
        while self._connected:
            try:
                import math
                async for pos in self.client.telemetry.position():
                    self._mark_telemetry_fresh()
                    self._telemetry.latitude = pos.latitude_deg if not math.isnan(pos.latitude_deg) else None
                    self._telemetry.longitude = pos.longitude_deg if not math.isnan(pos.longitude_deg) else None
                    self._telemetry.altitude = pos.relative_altitude_m if not math.isnan(pos.relative_altitude_m) else None
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"PX4 position subscription failed: {e}")
                if "AioRpcError" in str(type(e)) and ("UNAVAILABLE" in str(e) or "Stream removed" in str(e)):
                    pass # Stream dropped, let loop retry
                await asyncio.sleep(2.0)

    async def _subscribe_velocity(self):
        while self._connected:
            try:
                import math
                async for vel in self.client.telemetry.velocity_ned():
                    self._mark_telemetry_fresh()
                    self._telemetry.velocity_x = vel.north_m_s if not math.isnan(vel.north_m_s) else None
                    self._telemetry.velocity_y = vel.east_m_s if not math.isnan(vel.east_m_s) else None
                    self._telemetry.velocity_z = vel.down_m_s if not math.isnan(vel.down_m_s) else None
                    # calculate ground speed
                    if self._telemetry.velocity_x is not None and self._telemetry.velocity_y is not None:
                        self._telemetry.ground_speed = math.sqrt(vel.north_m_s**2 + vel.east_m_s**2)
                    else:
                        self._telemetry.ground_speed = None
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"PX4 velocity_ned subscription failed: {e}")
                if "AioRpcError" in str(type(e)) and ("UNAVAILABLE" in str(e) or "Stream removed" in str(e)):
                    pass # Stream dropped, let loop retry
                await asyncio.sleep(2.0)

    async def _subscribe_attitude(self):
        while self._connected:
            try:
                async for attitude in self.client.telemetry.attitude_euler():
                    self._mark_telemetry_fresh()
                    self._telemetry.roll = attitude.roll_deg
                    self._telemetry.pitch = attitude.pitch_deg
                    self._telemetry.yaw = attitude.yaw_deg
                    # normalize yaw to heading (0-360)
                    heading = attitude.yaw_deg
                    if heading < 0:
                        heading += 360.0
                    self._telemetry.heading = heading
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"PX4 attitude_euler subscription failed: {e}")
                if "AioRpcError" in str(type(e)) and ("UNAVAILABLE" in str(e) or "Stream removed" in str(e)):
                    pass # Stream dropped, let loop retry
                await asyncio.sleep(2.0)

    async def _subscribe_battery(self):
        while self._connected:
            try:
                import math
                async for battery in self.client.telemetry.battery():
                    self._mark_telemetry_fresh()
                    val = battery.remaining_percent
                    if val < 0 or math.isnan(val):
                        self._telemetry.battery_level = None
                    else:
                        # Some MAVSDK versions report 0-1, others 0-100.
                        pct = val if val > 1.0 else val * 100.0
                        self._telemetry.battery_level = max(0.0, min(100.0, pct))
                    self._telemetry.voltage = battery.voltage_v
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"PX4 battery subscription failed: {e}")
                if "AioRpcError" in str(type(e)) and ("UNAVAILABLE" in str(e) or "Stream removed" in str(e)):
                    pass # Stream dropped, let loop retry
                await asyncio.sleep(2.0)

    async def _subscribe_flight_mode(self):
        while self._connected:
            try:
                async for mode in self.client.telemetry.flight_mode():
                    self._mark_telemetry_fresh()
                    self._telemetry.flight_mode = str(mode)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"PX4 flight_mode subscription failed: {e}")
                if "AioRpcError" in str(type(e)) and ("UNAVAILABLE" in str(e) or "Stream removed" in str(e)):
                    pass # Stream dropped, let loop retry
                await asyncio.sleep(2.0)

    async def _subscribe_gps_info(self):
        while self._connected:
            try:
                async for gps_info in self.client.telemetry.gps_info():
                    self._mark_telemetry_fresh()
                    self._telemetry.gps_valid = gps_info.fix_type.name in ["FIX_2D", "FIX_3D", "FIX_DGPS", "RTK_FLOAT", "RTK_FIXED"]
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"PX4 gps_info subscription failed: {e}")
                if "AioRpcError" in str(type(e)) and ("UNAVAILABLE" in str(e) or "Stream removed" in str(e)):
                    pass # Stream dropped, let loop retry
                await asyncio.sleep(2.0)

    async def _subscribe_armed(self):
        while self._connected:
            try:
                async for is_armed in self.client.telemetry.armed():
                    self._mark_telemetry_fresh()
                    self._telemetry.armed_state = "ARMED" if is_armed else "DISARMED"
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"PX4 armed subscription failed: {e}")
                if "AioRpcError" in str(type(e)) and ("UNAVAILABLE" in str(e) or "Stream removed" in str(e)):
                    pass # Stream dropped, let loop retry
                await asyncio.sleep(2.0)

    async def _subscribe_health(self):
        while self._connected:
            try:
                async for health in self.client.telemetry.health():
                    self._mark_telemetry_fresh()
                    self._telemetry.health_all_ok = (
                        health.is_gyrometer_calibration_ok and
                        health.is_accelerometer_calibration_ok and
                        health.is_magnetometer_calibration_ok and
                        health.is_local_position_ok and
                        health.is_global_position_ok
                    )
                    self._telemetry.gyro_calibrated = health.is_gyrometer_calibration_ok
                    self._telemetry.accel_calibrated = health.is_accelerometer_calibration_ok
                    self._telemetry.mag_calibrated = health.is_magnetometer_calibration_ok
                    self._telemetry.local_pos_valid = health.is_local_position_ok
                    self._telemetry.global_pos_valid = health.is_global_position_ok
                    self._telemetry.is_armable = health.is_armable
                    self._telemetry.home_valid = health.is_home_position_ok
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"PX4 health subscription failed: {e}")
                if "AioRpcError" in str(type(e)) and ("UNAVAILABLE" in str(e) or "Stream removed" in str(e)):
                    pass # Stream dropped, let loop retry
                await asyncio.sleep(2.0)

    async def _subscribe_status_text(self):
        while self._connected:
            try:
                async for status in self.client.telemetry.status_text():
                    self._mark_telemetry_fresh()
                    if status.type.name in ["WARNING", "ERROR", "CRITICAL", "EMERGENCY", "INFO"]:
                        self._telemetry.status_text = status.text
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"PX4 status_text subscription failed: {e}")
                if "AioRpcError" in str(type(e)) and ("UNAVAILABLE" in str(e) or "Stream removed" in str(e)):
                    pass # Stream dropped, let loop retry
                await asyncio.sleep(2.0)

    def _empty_telemetry(self) -> TelemetryData:
        return TelemetryData(
            battery_level=None, altitude=None, latitude=None, longitude=None,
            velocity_x=None, velocity_y=None, velocity_z=None, flight_mode="disconnected"
        )

    async def get_all_params(self) -> dict:
        if not self._connected: return {}
        try:
            params = await self.client.param.get_all_params()
            res = {}
            for p in params.int_params:
                res[p.name] = p.value
            for p in params.float_params:
                res[p.name] = p.value
            return res
        except Exception as e:
            logger.error(f"Failed to get all parameters: {e}")
            return {}

    async def get_param(self, name: str, param_type: str = "float"):
        if not self._connected: return None
        try:
            if param_type == "int":
                return await self.client.param.get_param_int(name)
            else:
                return await self.client.param.get_param_float(name)
        except Exception as e:
            logger.error(f"Failed to get parameter {name}: {e}")
            return None

    async def set_param(self, name: str, value, param_type: str = "float") -> bool:
        if not self._connected: return False
        try:
            if param_type == "int":
                await self.client.param.set_param_int(name, int(value))
            else:
                await self.client.param.set_param_float(name, float(value))
            return True
        except Exception as e:
            logger.error(f"Failed to set parameter {name}: {e}")
            return False
