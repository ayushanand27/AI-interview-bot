import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import PasswordInput from "./PasswordInput";

describe("PasswordInput", () => {
  it("masks the value by default and reveals it on toggle", async () => {
    const user = userEvent.setup();
    render(<PasswordInput id="pw" />);

    const field = document.getElementById("pw") as HTMLInputElement;
    expect(field.type).toBe("password");

    await user.click(screen.getByRole("button", { name: /show password/i }));
    expect(field.type).toBe("text");
    expect(
      screen.getByRole("button", { name: /hide password/i }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /hide password/i }));
    expect(field.type).toBe("password");
  });
});
