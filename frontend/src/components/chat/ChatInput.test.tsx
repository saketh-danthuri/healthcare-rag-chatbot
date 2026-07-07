import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatInput } from "./ChatInput";
import { MAX_UPLOAD_BYTES } from "@/lib/constants";

vi.mock("@/lib/api", () => ({
  api: { uploadFile: vi.fn() },
}));

import { api } from "@/lib/api";
const uploadFile = api.uploadFile as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  uploadFile.mockReset();
});

function sizedFile(name: string, bytes: number): File {
  const file = new File(["x"], name, { type: "text/plain" });
  Object.defineProperty(file, "size", { value: bytes });
  return file;
}

function setup(overrides: Partial<React.ComponentProps<typeof ChatInput>> = {}) {
  const props = {
    onSend: vi.fn(),
    isLoading: false,
    ...overrides,
  };
  render(<ChatInput {...props} />);
  return props;
}

describe("ChatInput send behaviour", () => {
  it("disables Send when the input is empty", () => {
    setup();
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
  });

  it("sends trimmed text on click and clears the field", async () => {
    const user = userEvent.setup();
    const props = setup();
    const box = screen.getByRole("textbox");

    await user.type(box, "  restart the job  ");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(props.onSend).toHaveBeenCalledWith("restart the job", undefined, undefined);
    expect(box).toHaveValue("");
  });

  it("sends on Enter but inserts a newline on Shift+Enter", async () => {
    const user = userEvent.setup();
    const props = setup();
    const box = screen.getByRole("textbox");

    await user.type(box, "line one{Shift>}{Enter}{/Shift}line two");
    expect(props.onSend).not.toHaveBeenCalled();
    expect(box).toHaveValue("line one\nline two");

    await user.type(box, "{Enter}");
    expect(props.onSend).toHaveBeenCalledTimes(1);
    expect(props.onSend).toHaveBeenCalledWith("line one\nline two", undefined, undefined);
  });
});

describe("ChatInput generating state", () => {
  it("shows a Stop button while streaming and fires onStop", async () => {
    const user = userEvent.setup();
    const onStop = vi.fn();
    setup({ isStreaming: true, onStop });

    expect(screen.queryByRole("button", { name: "Send message" })).not.toBeInTheDocument();
    const stop = screen.getByRole("button", { name: "Stop generating" });
    await user.click(stop);
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("does not send while a response is already generating", async () => {
    const user = userEvent.setup();
    const props = setup({ isLoading: true });
    const box = screen.getByRole("textbox");
    // Textarea is disabled while loading; typing + Enter must not send.
    await user.type(box, "should not send{Enter}");
    expect(props.onSend).not.toHaveBeenCalled();
  });
});

describe("ChatInput file-size validation", () => {
  const fileInput = () =>
    document.querySelector('input[type="file"]') as HTMLInputElement;

  it("rejects an oversized file client-side without calling the API", async () => {
    const user = userEvent.setup();
    setup();

    await user.upload(fileInput(), sizedFile("huge.txt", MAX_UPLOAD_BYTES + 1));

    expect(uploadFile).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/too large/i);
  });

  it("uploads a file within the size limit and shows the attached chip", async () => {
    const user = userEvent.setup();
    uploadFile.mockResolvedValue({
      file_id: "f1",
      filename: "notes.txt",
      size_bytes: 10,
      preview: "hello",
    });
    setup();

    await user.upload(fileInput(), sizedFile("notes.txt", 1024));

    await waitFor(() => expect(uploadFile).toHaveBeenCalledTimes(1));
    expect(screen.getByText("notes.txt")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
