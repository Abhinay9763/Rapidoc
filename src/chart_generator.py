import matplotlib.pyplot as plt
import os

def generate_chart(spec: dict, output_path: str) -> str:
    """
    Generates a chart using matplotlib based on the spec and saves it to output_path.
    """
    try:
        chart_type = spec.get("chart_type", "bar")
        title = spec.get("title", "Generated Chart")
        
        # Use provided data or fallback to dummy data
        data = spec.get("data", {})
        x_data = data.get("x", ["Item 1", "Item 2", "Item 3"])
        y_data = data.get("y", [10, 20, 30])
        
        labels = spec.get("labels", {})
        x_label = labels.get("x", "X-Axis")
        y_label = labels.get("y", "Y-Axis")

        plt.figure(figsize=(6, 4))
        
        if chart_type == "bar":
            plt.bar(x_data, y_data, color='skyblue')
        elif chart_type == "line":
            plt.plot(x_data, y_data, marker='o', linestyle='-', color='green')
        elif chart_type == "scatter":
            plt.scatter(x_data, y_data, color='purple')
        elif chart_type == "pie":
            plt.pie(y_data, labels=x_data, autopct='%1.1f%%', startangle=140)
        else:
            plt.bar(x_data, y_data, color='gray') # default to bar

        plt.title(title)
        if chart_type != "pie":
            plt.xlabel(x_label)
            plt.ylabel(y_label)
            plt.tight_layout()
            
        plt.savefig(output_path, dpi=150)
        plt.close()
        return output_path
    except Exception as e:
        print(f"Failed to generate chart, creating fallback: {e}")
        # Create a fallback chart
        plt.figure(figsize=(6, 4))
        plt.text(0.5, 0.5, 'Chart Generation Failed\\n(Placeholder)', horizontalalignment='center', verticalalignment='center', fontsize=12)
        plt.savefig(output_path)
        plt.close()
        return output_path
