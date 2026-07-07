"use client";

import { useState, useRef, useCallback } from "react";
import { Send, Loader2, Paperclip, FileText, X, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { MAX_UPLOAD_BYTES } from "@/lib/constants";

interface AttachedFileState {
  fileId: string;
  filename: string;
}

interface ChatInputProps {
  onSend: (message: string, fileId?: string, filename?: string) => void;
  isLoading: boolean;
  /** True while a response is generating — turns Send into a Stop button. */
  isStreaming?: boolean;
  /** Aborts the in-flight generation. */
  onStop?: () => void;
  placeholder?: string;
}

export function ChatInput({
  onSend,
  isLoading,
  isStreaming = false,
  onStop,
  placeholder = "Ask about runbook procedures, job failures, or claims data...",
}: ChatInputProps) {
  const [input, setInput] = useState("");
  const [attachedFile, setAttachedFile] = useState<AttachedFileState | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const generating = isLoading || isStreaming;

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || isLoading || isStreaming || isUploading) return;
    onSend(trimmed, attachedFile?.fileId, attachedFile?.filename);
    setInput("");
    setAttachedFile(null);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [input, isLoading, isStreaming, isUploading, onSend, attachedFile]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const textarea = e.target;
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + "px";
  };

  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Reset file input so the same file can be re-selected
    e.target.value = "";
    setUploadError(null);

    // Validate size client-side before uploading (server enforces too).
    if (file.size > MAX_UPLOAD_BYTES) {
      const limitMb = Math.round(MAX_UPLOAD_BYTES / (1024 * 1024));
      setUploadError(`File is too large. Maximum size is ${limitMb} MB.`);
      return;
    }

    setIsUploading(true);
    try {
      const result = await api.uploadFile(file);
      setAttachedFile({ fileId: result.file_id, filename: result.filename });
    } catch (err) {
      console.error("File upload failed:", err);
      setUploadError("File upload failed. Please try again.");
    } finally {
      setIsUploading(false);
    }
  }, []);

  const handleRemoveFile = useCallback(() => {
    setAttachedFile(null);
  }, []);

  return (
    <div className="border-t bg-card px-4 py-3 shrink-0">
      <div className="max-w-3xl mx-auto">
        {/* Attached file chip */}
        {attachedFile && (
          <div className="flex items-center gap-1.5 mb-2">
            <div className="flex items-center gap-1.5 bg-primary/10 text-primary text-xs rounded-full px-3 py-1">
              <FileText className="w-3 h-3" />
              <span className="max-w-[200px] truncate">{attachedFile.filename}</span>
              <button
                onClick={handleRemoveFile}
                className="hover:bg-primary/20 rounded-full p-0.5"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          </div>
        )}

        {/* Uploading indicator */}
        {isUploading && (
          <div className="flex items-center gap-1.5 mb-2 text-xs text-muted-foreground">
            <Loader2 className="w-3 h-3 animate-spin" />
            <span>Uploading file...</span>
          </div>
        )}

        {/* Upload error (e.g. file too large) */}
        {uploadError && (
          <div className="flex items-center gap-1.5 mb-2 text-xs text-destructive" role="alert">
            <X className="w-3 h-3" />
            <span>{uploadError}</span>
          </div>
        )}

        <div className="flex items-end gap-2 bg-muted rounded-xl px-3 py-2">
          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt"
            onChange={handleFileSelect}
            className="hidden"
          />

          {/* Paperclip upload button */}
          <Button
            size="icon"
            variant="ghost"
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading || isUploading}
            className="h-8 w-8 shrink-0 rounded-lg text-muted-foreground hover:text-foreground"
            title="Attach meeting transcript (.txt)"
          >
            <Paperclip className="w-4 h-4" />
          </Button>

          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={isLoading}
            rows={1}
            className="flex-1 bg-transparent resize-none text-sm focus:outline-none placeholder:text-muted-foreground min-h-[36px] max-h-[200px] py-1.5"
          />
          {generating && onStop ? (
            <Button
              size="icon"
              variant="destructive"
              onClick={onStop}
              className="h-8 w-8 shrink-0 rounded-lg"
              aria-label="Stop generating"
              title="Stop generating"
            >
              <Square className="w-3.5 h-3.5 fill-current" />
            </Button>
          ) : (
            <Button
              size="icon"
              onClick={handleSend}
              disabled={!input.trim() || generating || isUploading}
              className="h-8 w-8 shrink-0 rounded-lg"
              aria-label="Send message"
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </Button>
          )}
        </div>
        <p className="text-xs text-muted-foreground text-center mt-2">
          AI responses are based on runbook documentation. Always verify critical procedures.
        </p>
      </div>
    </div>
  );
}
