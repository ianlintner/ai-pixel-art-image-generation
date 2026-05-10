import json

def create_image_batch_file(client, prompts, model="dall-e-3", size="1024x1024", quality="standard", output_file="batch_requests.jsonl"):
    batch_requests = []
    for i, prompt in enumerate(prompts):
        batch_requests.append({
            "custom_id": f"request-{i}",
            "method": "POST",
            "url": "/v1/images/generations",
            "body": {
                "model": model,
                "prompt": prompt,
                "n": 1,
                "size": size,
                "quality": quality
            }
        })
    
    with open(output_file, "w") as f:
        for req in batch_requests:
            f.write(json.dumps(req) + "\n")
            
    with open(output_file, "rb") as f:
        batch_file = client.files.create(file=f, purpose="batch")
        return batch_file.id

def run_batch_job(client, file_id):
    batch_job = client.batches.create(
        input_file_id=file_id,
        endpoint="/v1/images/generations",
        completion_window="24h"
    )
    return batch_job.id
