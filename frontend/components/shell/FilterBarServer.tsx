import { Suspense } from "react";
import { getVehicleTypesFilter } from "@/lib/api/client";
import { FilterBar } from "./FilterBar";

async function VehicleTypeAwareFilterBar() {
  let vehicleTypes: string[] = [];
  try {
    const res = await getVehicleTypesFilter();
    vehicleTypes = res.vehicle_types;
  } catch {
    // The filter bar itself must never blank the page -- fall back to an
    // empty list (just "All types") if the endpoint is unreachable.
    vehicleTypes = [];
  }
  return <FilterBar vehicleTypes={vehicleTypes} />;
}

export function FilterBarServer() {
  return (
    <Suspense fallback={<FilterBar vehicleTypes={[]} />}>
      <VehicleTypeAwareFilterBar />
    </Suspense>
  );
}
