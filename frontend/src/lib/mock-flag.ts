export function useMocks(): boolean {
  return process.env.NEXT_PUBLIC_USE_MOCKS === "1";
}
