/**
 * Name-keyed series color mapping -- never index-keyed, so a filtered
 * subset of vehicle types/tiers never recolors relative to the full set.
 * Real vehicle types (fee tiers), fixed ascending price order:
 * Porter -> Car -> Pickup bus -> Dyna/Canter -> Trailer.
 */

export const VEHICLE_TYPE_COLOR_VAR: Record<string, string> = {
  Porter: "--s1",
  Car: "--s2",
  "Pickup bus": "--s3",
  "Dyna/Canter": "--s4",
  Trailer: "--s5",
};

/** Fixed ascending fee-tier order for stacking -- stable regardless of filters. */
export const VEHICLE_TYPE_ORDER = ["Porter", "Car", "Pickup bus", "Dyna/Canter", "Trailer"];

export const VEHICLE_TYPE_PRICE: Record<string, number> = {
  Porter: 100,
  Car: 300,
  "Pickup bus": 600,
  "Dyna/Canter": 1200,
  Trailer: 3000,
};

const VEHICLE_TYPE_LABEL: Record<string, string> = {
  "Dyna/Canter": "Dyna/ Center",
  "Dyna Canter": "Dyna/ Center",
};

/** User-facing label for a backend vehicle-type value. */
export function vehicleTypeLabel(vehicleType: string): string {
  return VEHICLE_TYPE_LABEL[vehicleType] ?? vehicleType;
}

/** Fallback color var for a vehicle type not in the known map (defensive, shouldn't happen). */
export function vehicleTypeColorVar(vehicleType: string): string {
  return VEHICLE_TYPE_COLOR_VAR[vehicleType] ?? "--mu";
}

export function sortByVehicleTypeOrder<T extends { vehicle_type: string }>(items: T[]): T[] {
  return [...items].sort((a, b) => {
    const ia = VEHICLE_TYPE_ORDER.indexOf(a.vehicle_type);
    const ib = VEHICLE_TYPE_ORDER.indexOf(b.vehicle_type);
    const ra = ia === -1 ? VEHICLE_TYPE_ORDER.length : ia;
    const rb = ib === -1 ? VEHICLE_TYPE_ORDER.length : ib;
    return ra - rb;
  });
}
