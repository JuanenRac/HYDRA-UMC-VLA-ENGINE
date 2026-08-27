# Contributing to HYDRA-UMC-VLA-ENGINE 🦾

We welcome contributions to the Vision-Language-Action framework of the HYDRA-UMC platform.

## Technology Stack
- **Language**: Python 3.12.
- **Frameworks**: PyTorch, Hailo Dataflow Compiler.
- **Models**: OpenVLA, RT-2, Quantized VLA Variants.
- **Hardware**: Hailo-10 M.2 AI Accelerator (40 TOPS).

## Guidelines
1. **Model Generalization**: Ensure all VLA models are tested for zero-shot generalization on standard industrial datasets.
2. **Action Precision**: Validate that generated action tokens map accurately to 6-DOF robotic coordinates.
3. **Inference Latency**: Action generation must remain under 100ms for fluid robotic motion.
4. **Testing**: Use the `HYDRA-UMC-PHYSICS-REPLICA` to validate new action heads in simulation.
