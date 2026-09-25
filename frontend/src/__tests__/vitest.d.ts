// jest-axe only types its matcher for Jest; Vitest 5 no longer merges
// jest.Matchers into its own assertions.
import "vitest";

declare module "vitest" {
  interface Assertion<T = unknown> {
    toHaveNoViolations(): T;
  }
}
