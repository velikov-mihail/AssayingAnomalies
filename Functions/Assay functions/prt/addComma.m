function numOut = addComma(numIn)
   jf=java.text.DecimalFormat; % comma for thousands, three decimal places
   jf.setMaximumFractionDigits(0);
   numOut= char(jf.format(numIn)); % omit "char" if you want a string out
end