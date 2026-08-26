type RouteScore = { node_count: number; precision: number; hit_rate: number };
type RouteSet = Record<"topic" | "trick" | "combined", RouteScore>;
type RouteGate<Precision extends number, Hit extends number> = {
  precision: Precision;
  hit_rate: Hit;
};

export type MixQuality = {
  kind: "cross-kind-layout-v1";
  neighbor_count: 8;
  semantic_routes: RouteSet;
  projected_routes: RouteSet;
  position_eta_squared: number;
  exact_coordinate_duplicates: number;
  thresholds: {
    routes: {
      semantic: {
        topic: RouteGate<0.2, 0.75>;
        trick: RouteGate<0.2, 0.75>;
        combined: RouteGate<0.2, 0.75>;
      };
      projected: {
        topic: RouteGate<0.2, 0.5>;
        trick: RouteGate<0.2, 0.5>;
        combined: RouteGate<0.3, 0.5>;
      };
    };
    max_position_eta_squared: 0.05;
    max_exact_coordinate_duplicates: 0;
  };
};
